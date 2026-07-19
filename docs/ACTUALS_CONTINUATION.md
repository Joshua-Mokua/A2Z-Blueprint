# Actuals → live achievement — continuation note

**Written 2026-07-19, end of session. Committed engine fix at `e54a88f`.**

## The goal
Make the BSC Achievement column show real numbers: `actual / target` per KPI, sourced
from CBS, so the scorecards stop showing "—". Consumer scorecards (seeded this session)
are the first target.

## What is DONE and committed
- `utils/actuals_engine.py` — the `pillars_data` list/dict bug is fixed. The engine
  iterated `lib["pillars"].items()` but the library stores KPIs as a flat `kpis` list,
  so **the engine had never once completed a run** — which is exactly why no actuals
  store ever existed. It now completes: a run produced 30,236 rows.
- `ID_MAP` in that engine extended with the CBS-sourceable consumer KPIs:
  `NET_LOANS_ODS→loan_outstanding`, `TOTAL_DEPOSITS→total_deposits`,
  `NTB_CLIENTS→new_accounts_2026`, `CARD_NPL→npl_ratio`, and `CONSUMER_REVENUE`
  computed as `interest_income + fee_income`.
- Everything CBS can't source (card revenue, bancassurance, digital, MOU, NPS,
  DSA headcount, diaspora, all objectives) is **deliberately left manual** — the engine
  returns nothing for them rather than fabricating.

## What is VERIFIED about the data (don't re-litigate)
- CBS `accounts.csv` (200k rows) scopes to RM via `relationship_manager_code`, which
  MATCHES register staff codes. One RM had 3,455 accounts join cleanly.
- Deposit/loan bucketing is CORRECT. The engine buckets on the `category` column
  (`CASA`, `Term Deposit`, `Loan`), NOT `account_type_code`. FCASA and forex-term
  deposits fold into those two deposit categories — nothing dropped. My earlier
  "CASA-only bug" was a false alarm from reading the wrong column.

## The ONE open question that unblocks everything
**What does `utils/bsc_engine.py` `get_actual(staff_code, kpi_id, period)` read from?**

The scorecard (`bsc_score_computation.py:_get_actual`) does NOT read the xlsx or a
`kpi_actuals.json`. It calls `from utils.bsc_engine import get_actual`. So there is a
THIRD module in the chain, and its store is the real read target. Until we see what
`bsc_engine.get_actual` reads, we can't close the loop.

Next session, step 1: dump `utils/bsc_engine.py get_actual` and whatever it reads.

## The three plumbing issues to fix once the read store is known
1. **Doubled path.** `get_cbs_paths()` returns `a2z/data/` as the output folder, but the
   app/scorecard use `data/`. The engine wrote `a2z/data/actuals_2026_Jul_19.xlsx`.
   Confirm which folder `bsc_engine` reads and align the write to it.
2. **Copy-instead-of-build shortcut.** `compute_actuals_from_cbs` line ~289: if an
   existing `actuals_*.xlsx` is found it COPIES it and returns, skipping the CBS build
   at line ~312. That's why the run "Refreshed from actuals_2025_Dec_25.xlsx" — it used
   December's numbers, not fresh 2026. `force=True` bypasses only the line-226 cache
   check, not this shortcut. To build fresh 2026 actuals, this branch must be bypassed
   (or the 2025 xlsx moved out of the glob path).
3. **Format/loop close.** Engine writes xlsx; `bsc_engine.get_actual` reads its own
   store. Once both are known, ensure the engine writes what the reader reads, keyed by
   the same (staff_code, kpi_id, period) shape. This is the same write→read-mismatch
   family as the CR bug and the queue bug fixed earlier today.

## Discipline that worked all session (keep it)
- Read the real function before changing it. Every wrong turn today came from asserting
  a function's shape; every right one from dumping it first.
- Probe on Josh's machine — the sandbox is frozen/dataless since the repo went private.
- Confirm EFFECT, not status/return. A run that returns success=True still copied the
  wrong file.
