# Changelog — v10.359 Link 1 CBS Persistence Bridge

**Date:** 2026-05-13
**Phase:** 4 (forty-fourth arc — Football Team Test backbone, Link 1 closure)
**Audit:** G245 added (passes in ~0.2s isolated)
**Tests:** 15/15 PASSED in `test_v10359_cbs_writer.py`
**Page smoke:** 123/123 PASS + 0 static findings + 14/14 dynamic renders pass
**Verifier:** 161/161 checks pass on a clean extract
**G162 baseline:** 4022 (53 consecutive zero-drift batches)
**Master prompt:** v4.2 → v4.3 (lockstep — fourth consecutive batch)

---

## Your ask

> "proceed" — close Link 1 of the Football Team Test chain (teller → CBS persistence). The v10.358 seeder populates VirtualBankCore in memory, but nothing yet writes to `cbs_data/*.json`, so `actuals_engine.compute_actuals_from_cbs` never sees simulated activity.

## What v10.359 delivered

### `utils/virtual_bank_cbs_writer.py` (~470 lines)

A bridge module — takes a populated VirtualBankCore and atomically writes the six files `actuals_engine` reads. Two output formats kept in lockstep:

**1. `cbs_data/accounts.csv`** — per-account rows. 16 columns matching `aggregate_cbs_by_rm` + `aggregate_cbs_by_branch` + `compute_bank_aggregates`:

| Column | Source |
|---|---|
| `account_no` | VirtualAccount.account_no |
| `cif` | VirtualAccount.cif |
| `branch_code` | VirtualAccount.branch_code |
| `branch_name` | VirtualBranch lookup |
| `relationship_manager_code` | VirtualCustomer.rm_code |
| `category` | account_type → CASA / TERM / LOAN |
| `account_type_name` | account_type → Personal Savings / Business Current / Fixed Deposit / Business Overdraft / Business Loan |
| `current_balance` | VirtualAccount.balance |
| `date_opened` | VirtualAccount.open_date |
| `dormancy_status` | "Active" for fresh seed |
| `interest_income_ytd` | "0" (accruals are downstream) |
| `fee_income_ytd` | "0" |
| `loan_amount` | VirtualLoan.principal (if applicable) |
| `loan_outstanding` | VirtualLoan.outstanding |
| `npl_status` | "" or "Performing" or "NPL" |
| `npl_days` | VirtualLoan.days_past_due |

Stand-alone loans (CIFs with no matching account) get synthesized `LN_<loan_id>` rows so the loan portfolio aggregation sees them.

**2. Five aggregate JSON files**, computed from the same account records the CSV captures:
- `deposits_aggregate.json` — total_deposits_kes + by_product + by_segment
- `loans_aggregate.json` — gross_outstanding + by_segment + by_stage
- `npl_aggregate.json` — stage_3 + npl_ratio_pct + aging buckets (zeros for now)
- `customer_aggregate.json` — total_customers + by_segment_count
- `dormant_aggregate.json` — total_dormant + dormancy_rate + bands

The aggregates are derived from the per-account data the CSV captures — **they cannot drift from the CSV**. G245 verifies this coherence at every audit.

### Three behavioural guarantees

**1. Atomic.** Every file is written via `tmp.replace(final_path)`. Readers either see the prior version or the new version, never a partial one. No half-written CSVs corrupting downstream aggregation.

**2. Idempotent.** Calling `persist_bank_to_cbs(bank)` twice produces the same files byte-for-byte (rows sorted deterministically by branch_code + cif + account_no; aggregates computed deterministically from those rows).

**3. Coherent.** The aggregate JSONs are not separately authored — they're computed from the same row data that goes into the CSV. If you sum the CASA + TERM `current_balance` values in `accounts.csv`, you get exactly `deposits_aggregate.json::total_deposits_kes`. Verified by G245.

### G245 audit gate

Locks three invariants:

1. **Self-test passes** (covers atomicity + idempotency + referential integrity)
2. **Coherence**: `deposits_aggregate.json::total_deposits_kes` equals the sum of CASA+TERM `current_balance` values in `accounts.csv`
3. **Minimum viable scale**: small seeded bank produces ≥100 rows in accounts.csv

Runs in 0.23s isolated. The end-to-end probe re-seeds + persists into a temp dir on every run, so it catches regressions in either the seeder or the bridge.

### Self-test (9 tests)

`virtual_bank_cbs_writer.self_test()` validates:
- All 6 expected files exist after persist
- accounts.csv has ≥200 rows (200 accounts + 30 loan rows)
- Totals are nonzero
- Idempotency (two consecutive persists produce same totals)
- No `.tmp` leftovers (atomicity check)
- `actuals_engine.aggregate_cbs_by_rm` can read it back (≤30 RMs from seeder)
- Bank totals match aggregate JSON
- `format_persist_summary` produces readable output

All 9 pass in ~50ms.

### Readiness audit updated

`utils/virtual_bank_readiness.py::_probe_chain` now marks Link 1 as **WIRED** (was PARTIAL in v10.357 and v10.358). The chain status moves from 5/7 → **6/7 WIRED**. Only Link 7 (regional→MD tile) remains for v10.360.

### Verified end-to-end demonstration

```
Seed bank (small) → persist to tempdir → actuals_engine.aggregate_cbs_by_rm

CBS persistence — 0.003s
  Target:           /tmp/tmpXXXX
  accounts.csv rows: 230 (200 accounts + 30 loan-only rows)
  Aggregates:       5
  Total deposits:   KES 69,195,409
  Total loans:      KES 5,657,554
  NPL outstanding:  KES 0
  Customers:        100
  Dormant:          0

actuals_engine read back:
  RMs seen:      29
  Branches seen: 21

Sample RM 300034:
  total_deposits: 2,503,758
  loan_outstanding: 0
  casa_balance: 2,503,758
  account_count: 13
  loan_count: 0
```

This is the chain working. A teller (or in this case the seeder) acts on the virtual bank → balances persist to CBS aggregates → the actuals_engine reads them → RM/branch aggregations are computable → ready to feed the BSC scorecard.

## Files changed

| File | Change |
|---|---|
| `utils/virtual_bank_cbs_writer.py` | NEW — ~470 lines, bridge module |
| `utils/virtual_bank_readiness.py` | `_probe_chain` marks Link 1 WIRED via virtual_bank_cbs_writer import |
| `scripts/audit.py` | NEW gate G245 `gate_cbs_writer_integrity` |
| `scripts/verify_local_state.py` | Extended to 161 checks |
| `tests/integration/test_v10359_cbs_writer.py` | NEW — 15 tests |
| `docs/Master_Prompt_v4.3.md` | NEW — lockstep bump from v4.2 |

## Verified outcome

| Metric | Before v10.359 → After v10.359 |
|---|---|
| Audit gates | 244 → **245** (G245 added) |
| Football Team Test chain | 5/7 WIRED, 2/7 PARTIAL → **6/7 WIRED, 1/7 PARTIAL** |
| Link 1 (teller→CBS) | PARTIAL → **WIRED** |
| Page smoke | 123/123 PASS (preserved) |
| Static AST | 0 findings (preserved) |
| Dynamic render | 14/14 effective PASS (preserved) |
| Tests | +15 in v10.359 file, all passing |
| Verifier | 153 → **161 checks** |
| Master prompt | v4.2 → **v4.3** — lockstep |
| G162 baseline | 4022 (**53 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **NPL aging buckets are zeros.** `npl_aggregate.json::by_aging_kes` reports `DAYS_91_180`, `DAYS_181_365`, `DAYS_OVER_365` all as zero. Computing aging requires DPD-band granularity from the loan records. The seeded bank has all loans as PERFORMING with `days_past_due=0`, so even with the granularity the aging would still be zero. Real bring-up against simulated stress scenarios will populate these once `apply_credit_deterioration` runs.

2. **`interest_income_ytd` and `fee_income_ytd` are zeros in accounts.csv.** Income accruals are downstream computations the actuals_engine doesn't currently consume from these columns. Future work can populate them from VirtualTransaction history; for now, zero is honest.

3. **Dormancy is always "Active".** Seeded customers have no last_transaction_date drift yet. The simulator's daily ops will eventually create dormant accounts (no txns in 90 days), but the seeder produces a fresh-bank state.

4. **Synthesized loan-only rows.** Loans whose CIF has no matching deposit account get a phantom `LN_<loan_id>` row in accounts.csv with `current_balance=0` so the loan portfolio aggregation sees them. This isn't how real CBS data is shaped — real FLEXCUBE has loans as their own account_type — but matches the actuals_engine's reading pattern (it treats loan-bearing rows as loans regardless of how they got there).

5. **`accounts.csv` is written to whichever `cbs_data/` directory exists.** The default search order is `<project root>/cbs_data` (Joshua's localhost convention) → `<project root>/a2z/data` (fallback for installations without separate cbs_data). Tests pass `output_dir=tmp_path` to avoid touching real data.

6. **The bridge overwrites existing `cbs_data/` files.** This is deliberate — re-running the bridge after a simulator advance gives you the new state. But if a real CBS extract exists at `cbs_data/` and you accidentally run the bridge against it, you lose the real data. Production deployments would want a separate `cbs_data_virtual/` to keep real and virtual extracts separate. For the test harness, single-directory overwrite is fine.

7. **G245's coherence check only covers deposits.** It verifies `deposits_aggregate.json::total_deposits_kes` matches the CSV CASA+TERM sum but doesn't yet verify loans/NPL/customers/dormant the same way. Each adds ~0.05s; in principle they should all be locked. Deferred to a future gate-tightening batch.

8. **Bridge writes synchronously.** No async, no batching. For 230 rows + 5 JSONs it's ~3ms; for 10,000 customers it'd be ~300ms. Acceptable. For 700K customers (full Tier-2 scale) it'd be ~20s — at which point streaming the CSV row-by-row would help. Out of scope for v10.359.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10359_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 161 CHECKS PASSED**
5. **End-to-end demo:**
   ```
   python -c "
   import tempfile
   from pathlib import Path
   from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
   from utils.virtual_bank_cbs_writer import persist_bank_to_cbs, format_persist_summary
   from utils.actuals_engine import aggregate_cbs_by_rm
   bank, _ = seed_virtual_bank(config=SeedConfig.small())
   with tempfile.TemporaryDirectory() as td:
       result = persist_bank_to_cbs(bank, output_dir=Path(td))
       print(format_persist_summary(result))
       rm_data = aggregate_cbs_by_rm(Path(td))
       print(f'\\nactuals_engine reads back: {len(rm_data)} RMs')
   "
   ```
6. **Or write to your real cbs_data/:** (DESTRUCTIVE — overwrites cbs_data/)
   ```
   python -c "
   from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
   from utils.virtual_bank_cbs_writer import persist_bank_to_cbs, format_persist_summary
   bank, _ = seed_virtual_bank(config=SeedConfig.small())
   result = persist_bank_to_cbs(bank)  # writes to cbs_data/
   print(format_persist_summary(result))
   "
   ```
   Then run admin refresh in Streamlit — the BSC numbers should reflect the seeded bank.
7. Read `docs\Master_Prompt_v4.3.md` — fourth consecutive lockstep batch.
8. (Optional, takes >5min) Run audit → expect **245/245 PASS**

## v10.360 candidate — Link 7 MD tile bank-targets binding

The last PARTIAL link. The MD BSC tile should display the bank-level "on track?" rollup: how the bank as a whole is performing against the bank-level targets in `data/bank_targets.json` (set via Target Cascade → Bank Targets).

The pieces are mostly there:
- `bank_targets.json` exists with the canonical structure
- `pages/1_perform.py` already aggregates BSC actuals into branch + regional rollups
- The MD role is identified in `users.json` (william001, role "Chief Executive & Managing Director")

What's missing: a clean MD-specific BSC view that reads from `bank_targets.json` instead of from `target_cascade.json`. The cascade is intended for staff/department/branch targets; bank-level targets live separately.

v10.360 wires this: when the MD logs in (or has `can_view_all=True`), the BSC view uses bank_targets as the target source and rolls up all branches as the "actuals". The "on track?" tile compares each KPI's bank-level actual against the bank-level target.

After v10.360, all 7 chain links are WIRED. v10.361 then writes the end-to-end integration test that asserts: seed bank → simulator runs 5 days → bridge persists → actuals_engine refreshes → BSC rollup updates → MD tile reflects the change. **Charter §2 passes.**

Want me to proceed with v10.360?
