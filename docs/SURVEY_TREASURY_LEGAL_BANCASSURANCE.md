# What exists behind treasury, legal and bancassurance

**Surveyed 2026-08-19, before writing anything.** Four times this fortnight the
answer to "how do I build this?" turned out to be "where is it?" — the `/pick`
endpoint, the rework loop, the conditions model, the legal-officer dropdown.
So: survey first.

There is a great deal more here than I expected, and it is in three very
different states.

---

## Treasury — 43 routes, mounted, and none of them is the one you described

`utils/api_treasury.py` is live and substantial: ALM, LCR and NSFR, repricing
gaps, yield curves, FX and bond positions, mark-to-market, climate limits,
Islamic treasury, digital assets, a unified position board.

    /api/treasury/alm/register-deposit        a deposit as a BALANCE SHEET item
    /api/treasury/alm/register-rates-position
    /api/treasury/products/register-yield-curve
    /api/treasury/agents/approve              an agent workflow, not a rate one

**This is a treasury RISK and POSITION engine.** It answers "what do we hold,
what does it reprice at, are we within limits". It is not a dealing desk and it
has no notion of a branch asking for a price.

**What you described does not exist:** a branch raising a term-deposit request
— amount, tenor, requested rate — a manager recommending it, treasury pricing
it, a counter-rate coming back, and the branch accepting or declining. There is
no request object, no rate quote, no counter-offer, no round trip.

**But almost none of it needs building from scratch**, because the shape is one
we already have working: it is the credit committee flow with different words.

    a branch raises a case            the deal
    a manager recommends              the branch committee gate
    treasury prices it                the decision, with a value attached
    a counter-rate comes back         a decline that returns to the owner,
                                      which AC1 already does
    the branch accepts or declines    accept-decline, which already exists
    it closes                         Closed Won / Closed Lost

The recommendation engine, the queue, the vote-once rule, the return-to-owner
path, the journey — all of it is built and tested. What is missing is a **term
deposit request** carrying amount, tenor and requested rate, and a **treasury
desk** as the deciding party instead of a credit committee.

---

## Legal — 16 routes, mounted, and no screen at all

`utils/api_legal.py` covers matters, contract review, clauses, counsel,
documents, obligations, legal holds with acknowledgments, spend, and analytics.

    /api/legal/cases/board          /api/legal/holds/board
    /api/legal/contract-review/board /api/legal/obligations/board
    /api/legal/spend/board          /api/legal/analytics/portfolio-health

**Every one of these is a `board` endpoint — a read.** There is no screen in the
React app for any of it, and the only legal touch point that exists in the UI is
the charging assignment inside credit admin, which was broken until yesterday.

This is the cheapest of the three to surface: the data is there, the shapes are
settled, and a page per board would put it in front of people.

---

## Bancassurance — five modules, no router, nothing reachable

`insurance_catalog`, `insurance_claims`, `insurance_partner_hub`,
`insurance_recommendation`, `insurance_customer_rm_desktop`,
`insurance_commission_recon`, `insurance_ira_compliance` — around 80 public
functions between them.

**None of them exposes a router.** Nothing is mounted, so nothing is reachable
from the API at all. The logic exists as a library nobody can call.

That is a different job from the other two: legal needs a screen, treasury needs
a workflow, and bancassurance needs **an API surface first** — routes over the
existing functions — before a screen makes any sense.

---

## What I would do, in this order

**1. Term deposit rate approval.** Highest value, and mostly assembly rather
than invention. It reuses the recommendation engine, the queue, the
return-to-owner path and the journey. The new parts are small: a request with
amount, tenor and requested rate; treasury as the approving party; a
counter-rate that comes back rather than a plain decline.

**2. Legal boards.** 16 endpoints already returning data, no screen. A page per
board is a day's work and puts a whole function in front of its users.

**3. Bancassurance.** Routes first, over the existing modules, then a screen.
The largest of the three and the only one with nothing reachable today.

## Two questions before I build the term deposit flow

**Who prices it?** Treasury as a named desk, a committee like the others, or a
role — Head of Treasury, the FX dealers? The Business Credit Committee took
three attempts to get right because we settled who chairs it late.

**Is a counter-rate a decline or its own thing?** If treasury comes back at 9%
against 11% asked, is that a decline the branch may appeal, or a live offer the
branch accepts or rejects? They behave differently and the difference matters to
whoever is watching the queue.
