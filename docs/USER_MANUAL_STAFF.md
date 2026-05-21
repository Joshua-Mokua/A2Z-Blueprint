# A2Z MIS 360 — Staff User Manual

This manual is for staff who use A2Z to track their personal performance,
log activity, and contribute to their team's pipeline. If you are a
team lead or manager, see the
[Manager User Manual](USER_MANUAL_MANAGER.md) instead.

## What A2Z is for

A2Z MIS 360 is the bank's performance management platform. It pulls
data from the Core Banking System (FLEXCUBE), the loans system, the
AML platform, and the deal pipeline, and gives you a single dashboard
showing how you're tracking against your KPIs.

You'll use it for:
- Looking at your **balanced scorecard** (BSC) — your KPIs, your scores,
  your performance band
- Logging deals and tracking the pipeline
- Filing referrals to other units
- Submitting purchase requests and getting approvals
- Reviewing AML alerts assigned to you
- Managing your tasks via the activity log

## Logging in

Open the URL your IT team gave you. Enter your username (typically
`firstname###`, e.g. `jane002`) and password.

If you forget your password, click "Forgot Password" — an admin will
reset it for you. Default initial passwords are formatted
`ECOStaff` + the last 4 digits of your staff code (e.g. for staff
code `300042` the initial password is `ECOStaff0042`). **Change this
on first login.**

## The home page

After login, you land on the home page. It shows:

| Section | What it tells you |
|---|---|
| **Welcome banner** | The current period and any bank-wide announcements |
| **My BSC** | Your overall score (1.0–5.0) and band (Did Not Meet → Exceeded By Far) |
| **Pillar breakdown** | Your performance across the 4 BSC pillars |
| **Action items** | Pending tasks: late deals, unresolved AML alerts, pending approvals |
| **Quick links** | Shortcuts to the modules you use most |

The score updates **once per day** at 02:00 from the previous day's
data. If a number looks stale, it usually is — wait until tomorrow,
or contact an admin if there's a real discrepancy.

## Reading your BSC scorecard

Go to **Performance → My Scorecard**.

Each row is a KPI. Columns show:
- **KPI** — the measure name
- **Target** — what you should achieve this period
- **Actual** — what you've achieved so far
- **Achievement %** — actual ÷ target × 100
- **Score** — converted to the 1–5 BSC scale
- **Weight** — how much this KPI contributes to your overall score
- **Pillar** — which BSC pillar (Financial / Customer / Operational / People)

The **score** colour tells you the band:
- 🟢 **4.5–5.0** — Exceeded By Far
- 🟢 **3.5–4.4** — Exceeded
- 🟡 **3.0–3.4** — Met
- 🟠 **2.0–2.9** — Partially Met
- 🔴 **1.0–1.9** — Did Not Meet

### Tips for reading scorecards
- **Reverse-direction KPIs** (NPL, dormancy, error rate) score 5 when the
  number is LOW. Don't be confused if a small actual maps to a high score.
- **Achievement above 100%** keeps adding score — capping is at 130%
  for full 5.0.
- **Some actuals are computed nightly from FLEXCUBE/CBS** (deposit
  growth, loan book) — others are computed from your activity (deals
  closed, alerts resolved). Both feed the same scorecard.

## Logging activity

### Pipeline deals

Go to **Pipeline → Deals → New Deal**.

Required fields:
- **Client name** (and CIF if known)
- **Stage** — Initial Contact → Qualified → Proposal → Negotiation → Won/Lost
- **Deal category** — Trade Finance, Lending, Treasury, etc.
- **Unit** — your business unit
- **Value** + **Currency**
- **Open date**
- **Expected close date**

Update the **stage** as the deal progresses. Stage changes are
audit-logged with your username and timestamp.

When a deal moves to **Won**, you're prompted for the actual close
amount and any commission split with co-bankers. This feeds the
"Deals Closed (KES)" KPI.

### Referrals

Go to **CRM → Referrals → New Referral** to refer a client to another
unit (e.g. a Personal Banker referring to Trade Finance).

Both you and the receiving banker get credit when the referred deal
closes. The credit split defaults to 70/30 (originator/receiver) and
is configurable in admin.

### AML alerts

If an AML alert is assigned to you, you'll see a notification on the
home page. Open **AML → My Alerts** to review.

For each alert:
- Read the case detail
- Decide: Close (false positive), Escalate (to compliance team), or
  Request More Info (back to the analyst)
- Add a disposition comment — this is part of the regulatory record

The KPI "AML alerts cleared on time" measures whether you closed
each alert within its SLA window.

### Purchase requests

Go to **Operations → Purchase Requests → New** for any office-supplies
or vendor-engagement request. The workflow is:

1. You file the PR with description, vendor, estimated cost
2. Your manager approves
3. Procurement processes
4. Finance pays

Status updates are visible on your PR list. Track them via the
"Open POs > 30 days" KPI in your scorecard.

## My tasks page

Go to **Home → My Tasks** for a unified inbox of:
- Late pipeline deals (no stage update in 14+ days)
- Open AML alerts past SLA
- Pending purchase requests awaiting your input
- Referrals you've sent that haven't been actioned
- Loan applications stuck at your stage

Clear this list daily — your **task SLA compliance** is a People & Learning
KPI.

## Common questions

### "My score went DOWN, but I closed a deal — how?"

Several possibilities:
1. The deal value was below your target rate
2. Another KPI worsened (e.g. a loan you booked went into NPL)
3. A pillar you're weighted on heavily had a bad month even if your
   one KPI improved

Open **Performance → My Scorecard → "Why did this change?"** for a
diff against last period.

### "I see an actual that doesn't look right"

If you suspect a computation bug (not just a number you don't like):
1. Check the **Source** column on the scorecard — it tells you which
   module produced the value
2. Drill down into that module (e.g. Pipeline if Source=`pipeline`)
3. Verify the underlying records
4. If the records are correct but the score is wrong, file a ticket
   via **Help → Report a Computation Issue**. Include screenshots.

### "Can I appeal a score?"

The score itself is computed from data; it can't be "appealed". But you
can:
- Correct an underlying record (e.g. a deal value entered wrongly)
- Flag a target as unrealistic for next period (your manager handles this)

### "My password expired"

Default policy: passwords expire every 90 days. You'll be prompted on
login. Choose a strong password (12+ chars, mixed case, digits, symbol).

### "I logged in from a new computer and got blocked"

A2Z does not auto-block based on location. If you're blocked, it's
either an admin action or your account is disabled. Contact admin.

### "I'm seeing data from another user"

You shouldn't be — this is a security issue. **Log out immediately**
and report it to admin or IT security. Include a screenshot and the
URL.

## What you DON'T do here

- **Approve transactions** — A2Z is a reporting + workflow platform,
  not a transaction system. Use FLEXCUBE for actual money movement.
- **Override BSC scores** — only authorised admins (Director Retail,
  CEO) can do this, and every override is audit-logged.
- **Edit other people's records** — even if you have the data right
  in front of you, route corrections through the originating user or
  an admin.

## Quick keyboard shortcuts

The Streamlit UI doesn't have many global shortcuts, but useful ones:

- `r` — refresh (forces a re-render with latest data)
- `c` — clear cache (admin only; works only on cache pages)
- Browser back/forward navigates between pages

## Where to get help

- **In-app help** — Help → User Guide (this document)
- **Slack** — `#a2z-support` channel
- **Email** — `a2z-help@<bank>` for non-urgent issues
- **Phone** — IT helpdesk (after-hours / urgent)

For self-service:
- Try refreshing the page (browser refresh, then Streamlit's "Rerun" button)
- Log out and back in (clears session state)
- Try a different browser (Chrome / Edge are best supported)
