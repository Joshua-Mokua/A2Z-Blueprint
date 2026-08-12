# The mandatory credit spine

**Status:** proposed, 2026-08-12. Not built. Two decisions below need your
answer before anything is written.

## What you asked for

Uniformity across product lines. Every lending product follows the same
skeleton; admin adds mini-stages between the fixed points, and those vary by
product. Enforced, not merely defaulted — so a product cannot be created or
saved without it.

**Branch-originated**

```
Documentation
  -> Branch Credit Committee Review
  -> Department Credit Analysis
  -> Department Credit Committee Review
  -> Credit Analysis
  -> Credit Administration
  -> Trops
  -> a closing stage
```

**Not branch-originated** (CIB RMs, some Commercial) — the branch committee
does not apply:

```
Documentation
  -> Department Credit Analysis
  -> Department Credit Committee Review
  -> Credit Analysis
  -> Credit Administration
  -> Trops
  -> a closing stage
```

## What is already true

Three products — **Mortgage, Invoice Discounting, Trade Finance LC** — already
carry exactly this spine. So the naming below is not invented; it is what those
flows use and what the rest should be brought to.

**Measured:** of the 12 Asset products, **7 already carry the spine exactly** —
Invoice Discounting, Mortgage, Structured Finance, Term Loan, Trade Finance,
Trade Finance LC, Trade Finance. Only **5 need migrating**: Asset Finance,
Bundled Loan Product, Business Loan, Overdraft, Personal Loan.

That is a much smaller job than it looked, and it means the spine is already
the de facto standard rather than something being imposed.

Those five use an older shape:

```
Lead -> Contacted -> Qualified -> Credit Analysis & Assesment
     -> Credit Assessment - BCC -> Offer / Proposal -> Negotiation
     -> Credit Admin -> Closed - Trops
```

Different names for the same steps, and two spellings that reach users:
*Assesment*, and *Credit Analyst & Assesment* on Overdraft.

**Which products this applies to** has a clean answer already in the config:
`product_catalogue` is classed, and **Assets** holds the 12 lending products.
Liabilities, Transactional, Insurance and Investments are not credit and must
not be forced through a credit committee.

## How enforcement would work

`_validate_product_flow` already runs on every product-flow save. The spine
check goes there, so a flow that breaks it is refused with a reason rather than
saved and discovered later.

The rules:

1. **Every Asset product must contain the spine stages, in order.** Extra
   stages may sit anywhere between them. None of the spine may be removed or
   reordered.
2. **Every product — all classes — must end with a closing stage.** This is the
   fault behind the fixed deposit nobody could close, and behind twelve more
   flows in the same state.
3. Non-Asset products are checked for rule 2 only.

## The two decisions I need from you

**1. How does a CIB deal skip the branch committee?**

The spine differs by *deal*, but a flow is per *product*. One product serves
both a branch RM and a CIB RM.

The committee side already solves this: `_effective_committee_journey` drops
branch-only committees for a deal with no branch. The stage side does not — a
CIB deal would still have to walk through *Branch Credit Committee Review*.

I would make the advance path skip it: if the next stage is the branch
committee and the deal is not branch-originated, advance to the one after. One
flow, both journeys, consistent with how committees already behave.

The alternative is two flows per product, which doubles the admin work and the
ways they can drift apart. I do not recommend it.

**2. What happens to the nine products already on the old shape?**

Enforcing on save alone changes nothing for them until somebody edits them —
so the uniformity you want would not arrive.

Three options:

- **Report only.** A script lists which products violate the spine; admin fixes
  them. Safest, slowest, and it may never finish.
- **Migrate, with the plan shown first.** A script maps old names to spine
  names — *Credit Assessment - BCC* to *Branch Credit Committee Review*, and so
  on — shows exactly what it will do per product, and applies on `--apply`.
- **Migrate silently on save.** No. A flow changing under an admin who opened
  it to fix a typo is how trust in the config goes.

I would do the second. But **renaming a stage moves live deals**: a deal
sitting at *Credit Assessment - BCC* has to land somewhere sensible, and that
mapping is a judgement about the bank's process, not a lookup. I would want to
show you the deal counts per stage before touching anything.

## What this does not cover

**SLAs per stage.** You mentioned them. `target_days` already exists per stage
in the flow, and the spine would carry defaults — but the numbers are the
bank's, not mine to invent. Worth setting once the stage names are uniform,
because setting them now means setting them twice.

**The pilot.** Forcing the spine there is the same code; it travels in a
release. But it should be applied here first and watched, because a validator
that refuses a save the bank needs to make is worse than an inconsistent flow.
