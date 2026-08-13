# One deal store

**Status:** proposed, 2026-08-13. Not built. Read this before the code exists,
because the shape of the change matters more than the size of it.

## The ruling

> Clean, and let's have one state. A bank system of this magnitude needs to be
> DB led.

Agreed, and the evidence is now measured rather than suspected.

## What is actually true today

Deals live in two places, and nothing keeps them in step.

```
data/pipeline_deals.json     PipelineManager loads this, always, and only this
pipeline_deals (Postgres)    the API reads this, because
                             _PIPELINE_READ_DB_FIRST is True
```

Measured on the development box on 2026-08-13:

```
JSON  33 deals        DB  48 deals
in both and identical     4
in both but DIFFERENT    26        <- the dangerous ones
only in JSON              3
only in the DB           18
```

The differences are not cosmetic. Twenty-six deals disagree on **stage** —
`json='Documentation'` against `db='Offer Letter'`. Two screens each show
something, and they contradict each other.

Every mismatch chased this week traces here: a committee queue listing a case
whose Review button opened an empty page; a validation count of 1 above a list
showing nothing. Not corruption. Two stores and no reconciliation.

## Why it is not a one-line change

`PipelineManager` is a JSON object with an in-memory list:

```python
self.deals = self._load(self.deals_file)     # json.loads, nothing else
def _save_deals(self): self.deals_file.write_text(json.dumps(self.deals))
```

The API does know how to talk to the table — `_db_sync_pipeline_deal` (157
lines) maps a deal dict onto 21 columns plus a `metadata` JSONB catch-all, and
`_normalize_db_deal_row` (67 lines) unpacks it back. Twenty-two call sites use
the sync.

**Both of those live in `utils/api.py`, and `utils/core.py` cannot import
`utils/api.py` — that is circular.** So `PipelineManager` cannot reach the
mapping that already exists, which is precisely why it was left on JSON.

That is the actual obstacle. Not the database, not the schema: a module
boundary drawn before the migration started.

## The change

**1. Move the mapping to a module both sides can import.**

`utils/pipeline_store.py` holds `to_row()` and `from_row()` — the existing
bodies of `_db_sync_pipeline_deal` and `_normalize_db_deal_row`, moved rather
than rewritten. `api.py` keeps its two function names as thin wrappers so all
22 call sites stay untouched.

Nothing behaves differently after this step. It exists so the next one is
possible.

**2. `PipelineManager` reads the database when the table is live.**

```python
if db.table_uses_db("pipeline_deals"):
    self.deals = [from_row(r) for r in db.fetch_all("SELECT * FROM pipeline_deals")]
else:
    self.deals = self._load(self.deals_file)     # unchanged fallback
```

The fallback is not a nicety. The pilot has fallen back to JSON before and a
committee queue went empty; anything that assumes Postgres is answering will
fail the same way.

**3. `_save_deals` writes the database first, then mirrors to JSON.**

The upsert is the write that counts. The JSON file becomes a cold copy — useful
for reading a deal in a text editor at three in the morning, authoritative for
nothing.

**4. The reconciler runs before and after.**

`scripts/reconcile_deal_stores.py` already reports both stores. Its numbers are
the acceptance test: the divergence must be settled before the switch, and zero
after it.

## The decision this needs from you

**Twenty-six deals disagree on stage right now. Which side wins?**

A script cannot know whether `Documentation` or `Offer Letter` is where a case
actually sits. Three options:

- **The database wins.** It is what every screen has been showing, so it is
  what people have been acting on. Simplest, and probably right.
- **The most recently updated wins.** Defensible, but `updated_at` is itself
  written by both paths and cannot be trusted to be comparable.
- **Settle them by hand.** Twenty-six is not many, and on the development box
  they are mostly test data. On the pilot box the number may be different, and
  that is the number that matters.

**Run the reconciler on the pilot before deciding.** If the bank's divergence
is zero, this becomes a clean switch. If it is not, the list of disagreeing
deals is a conversation with the bank, not a script's decision.

## What this does not cover

**Activities** are in the same shape — `pipeline_activities.json` with no table
read. They should follow, but after deals are proven.

**Other managers.** `UserManager` and the rest have their own stores. This note
is deals only, deliberately: one migration, proven, before the pattern is
repeated.

## Testing

The existing walkthroughs become the acceptance test, run before and after:

```
scripts/simulate_branch_committee.py     a case through the committee
scripts/audit_deal_journey.py            capture to disbursement
scripts/reconcile_deal_stores.py         zero divergence
scripts/diag_committee_queue.py          the queue matches the detail page
```

Plus one that does not exist yet and should: a **field-level round trip** —
write a deal with every field populated, read it back through the DB path, and
assert nothing was lost. The `metadata` JSONB catch-all is where fields go to
disappear quietly, and nothing currently checks that they survive.
