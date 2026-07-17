# One truth, two places

**Recorded 2026-07-17, after three bugs in two days that were all the same bug.**

Every one of them was a list maintained by hand in one place and needed in two. Someone
extended one copy. Nothing failed. The system kept returning 200s and cheerful empty
results, and the damage only surfaced when a human clicked through the UI.

## The three

**1. `DEP_GROWTH` (fixed 8e169a9).** A legacy code was promoted to a real KPI id, but its
alias was left pointing at a *different* KPI. Resolution order was fixed so the real id
won; the alias stayed, dormant, waiting for someone to reorder that check.

**2. The Postgres mirror (fixed a662932).** `_db_sync_pipeline_deal` writes an allowlist
of ~71 deal fields into a `metadata` blob; `_normalize_db_deal_row` lifts a *second*
hand-written list back out. `cr` was on neither. So the Credit Report was written to the
JSON store, never reached Postgres, and every Postgres-first read lost it. `cr_ok` was
permanently false and **submit-to-credit refused every deal in the bank, for ever**, with
a message telling the RM to complete the thing they had just completed.

The comment above that block reads: *"Phase B0: persist the remaining deal fields so PG
is a COMPLETE mirror (these were JSON-only and vanished under PG-first reads)."* Someone
had already done this exercise, for exactly this reason, and still missed a field.
`document_files` and `documents_provided` are on both lists — which is why attachments
worked and the CR didn't.

**3. Global stages vs product flows (fixed b57ddd3).** `get_pending_validations` filtered
on the global `STAGE_NAMES`. Per-product flows define their own stages: Personal Loan
opens at `Initiation`, and 38 flows use `Proposal` or `Documentation` (note `Proposal` is
not `Offer / Proposal` — a different string). Deals at those stages matched nothing and
never appeared in any manager's validation queue. Since submit-to-credit requires manager
validation, **no consumer loan could reach credit at all.**

## What they have in common

- The second copy is **derived, not declared**. Nothing in the code says "these two lists
  must agree", so nothing can notice when they stop agreeing.
- Failure is **silent and plausible**. A dropped field looks exactly like a field that was
  never set. An unmatched stage looks exactly like an empty queue.
- The blame **lands on the user**. "Complete the CR first" to someone who just did. An
  empty queue to a manager with a deal waiting.

## Rules

1. **When one truth needs two representations, derive the second or test the pair.** Never
   maintain both by hand. If a mirror has a write list and a read list, a test must
   round-trip a fully-populated record and assert nothing was lost.
2. **When a migration promotes a legacy code to a canonical id, delete its alias in the
   same commit.** A dead alias is a loaded gun.
   (`tests/test_bsc_library_integrity.py` asserts this.)
3. **Don't test membership of a global list when the domain is configurable.** Ask what
   you mean. The queue meant "not closed", so it should say `stage not in terminal` — not
   `stage in STAGE_NAMES[idx:]`. Then a flow can rename its stages freely.
4. **A save that didn't save must raise.** `save_deal_cr` returned 200 while its own
   response body said `completed: false`. It was reporting the failure and nobody was
   reading. Assert the effect before returning success.

## How they were found

Not by reading the code. Every one was found by driving the live system:
`demo_dry_run.py` (real logins, real uploaded bytes, checks the effect not the status
code), and — for the queue — by a human clicking through the UI, because the API script
advanced the stage before validating and walked straight past it.

The corollary: **a green test suite that never exercises the real path proves nothing.**
`scripts/simulate_credit_chain.py` passed `documents_provided` as a list of names and
`attachment_filename` as a string. No byte was ever uploaded. It was green throughout the
entire period in which the credit chain was completely broken.
