# CHANGELOG v10.267 — Returns Calendar enrichment with persisted history

**Date:** 2026-05-07
**Theme:** Phase 3 of CBK persistence layer. Surfaces persisted
CbkReturnPackage history in the Returns Calendar tab so users can
see the latest generation per return code at a glance.
**Audit gates: 163/163 PASS. Lines added: ~75.**

## What v10.267 ships

New "📈 Recent Generations from Auto-Generators" expander appears at
the bottom of the Returns Calendar tab. Reads
`cbk_returns_generated.json` via `db.dual_load` (G2-compliant), then
shows two views:

### 1. Latest generation per return code (summary table)

```
Code | Latest period | Last generated      | By     | Severity      | Description
-----+---------------+---------------------+--------+----------------+-------------
LXP  | 2026-04       | 2026-05-07 11:43:10 | joshua | 🟢 NONE         | 8 large exposures...
OPR  | 2026          | 2026-05-07 11:43:10 | joshua | 🟢 NONE         | OPR-RWA share 21.64%...
SBL  | 2026-04       | 2026-05-07 11:43:10 | joshua | ⛔ SEVERE_BREACH | top borrower B001 at 0.3333...
```

One row per unique return_code, latest by `generated_at`.

### 2. Last 10 generations chronologically

Time-ordered history view showing the 10 most recent rows across all
return codes. Useful for "what did we generate today?" queries.

### Severity emoji map

```
NONE          → 🟢
MARGINAL      → 🟡
BREACH        → 🔴
SEVERE_BREACH → ⛔
```

### Empty state

Before any generations have happened:

```
💾 No generations persisted yet. Generate a return via Submit Return
   → BSD or Risk-Based Auto-Generators to populate this section.
```

## G2-compliant I/O

The first attempt used `_gen_path.read_text() + json.loads()` which
caught a G2 direct_io violation. Switched to:

```python
from utils.db import db as _gen_db
_gen_rows = _gen_db.dual_load(
    DATA / "cbk_returns_generated.json",
    table="cbk_returns_generated",
    index_cols=("id",))
```

This routes through the centralized I/O seam — reads from PG when
the table is migrated, JSON otherwise. Same pattern as v10.265's
save_cbk_package + v10.266's bugfix.

## Files changed

```
pages/74_cbk_returns.py    MOD  +75 lines (Recent Generations enrichment)
```

## Audit

```
163/163 PASS
G162: 3,663 holding at baseline (no new tokens)
G163: GROWING (DDL 27→32, MIGRATORS 17→18) — partnership cluster
      still in flight; baseline raise deferred
```

## Smoke test verified

Wrote 3 packages (SBL/LXP/OPR) via save_cbk_package, then rendered
calendar tab. Per-code summary correctly shows latest by code with
severity emoji. History view shows 3 rows in reverse chronological
order. Empty state confirmed by deleting the file.

## CBK persistence layer status (after v10.267)

```
✅ DDL (v10.265)
✅ Migrator (v10.265)
✅ Save helper (v10.265 + bugfix v10.266)
✅ UI wiring — 5 Risk-Based tabs (v10.266)
✅ Calendar enrichment — Recent Generations (v10.267) THIS BATCH
⏳ UI wiring — 4 BSD tabs (v10.268)
```

After v10.268, all 9 generation paths persist + history is queryable.

## Honest acknowledgements

1. **The summary table joins by return_code, not name.** Because
   the periodic registry uses codes CBK1-CBK47 while generations use
   CAR/LIQ/SBL/LXP/FXE/NPL/IRR/OPR (and from v10.268 also
   BSD-1/2/3/17), the summary table is independent — no join with
   the calendar's primary table. This is intentional; mapping
   "Single Obligor Limit" → SBL is brittle.

2. **Latest-per-code uses string comparison on generated_at.**
   ISO-8601 strings sort correctly chronologically, so this works.
   Future polish: parse to datetime for type safety.

3. **64 consecutive clean batches** — v10.193 through v10.267.
