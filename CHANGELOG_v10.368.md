# Changelog — v10.368 SBU PBT Reconciliation

**Date:** 2026-05-13
**Phase:** 4 (fifty-third arc — first concrete unification step)
**Audit:** G254 added (passes — locks Σ(SBU PBT) = Bank PBT within KES 100)
**Tests:** 15/15 PASSED in `test_v10368_sbu_reconciliation.py`; 136 prior tests unchanged = **151 total**
**Page smoke:** 123/123 PASS + 0 static findings + 14/14 dynamic renders pass
**Verifier:** 235/235 checks pass on a clean extract
**G162 baseline:** 4022 (62 consecutive zero-drift batches)
**Master prompt:** v4.11 → v4.12 (lockstep — thirteenth consecutive batch)

---

## Your ask

> "proceed with the best option, unification"

You gave me the call on Q1 (canonical engine), Q3 (allocation driver default), and ordering. Decisions:

- **Q1: Engine A canonical.** It's what the MD's BSC reads + what bank_targets.json compares against + what FLEXCUBE will provide in production. Engine B becomes a downstream consumer (refactored last, v10.372).
- **Q3: FTE-weighted default (configurable).** Matches `cost_allocation_rules.json::RULE_001` pattern. Admin can switch via the new allocation rules config (lands in v10.369).
- **Ordering: SBU first.** Highest-value-per-batch — `opex_data::by_sbu` already populated, MD gets per-SBU drill-down immediately, establishes the first reconciliation identity. Renumbered: this is v10.368, per-branch is v10.369, per-RM is v10.370, multi-level targets is v10.371, Engine B refactor is v10.372.

## What v10.368 delivered

### The reconciliation identity, locked

```
Per-SBU PBT Breakdown
========================================================================================
SBU                          OpIncome                   OpEx                    PBT
----------------------------------------------------------------------------------------
Retail Banking         KES   -396,663  KES -3,100,000,000  KES -3,100,396,663
Commercial Banking     KES   -573,979  KES -2,000,000,000  KES -2,000,573,979
Corporate Banking      KES   -269,437  KES   -900,000,000  KES   -900,269,437
Treasury               KES          0  KES   -400,000,000  KES   -400,000,000
Digital / Agency       KES          0  KES   -800,000,000  KES   -800,000,000
Unallocated            KES          0  KES   -700,000,000  KES   -700,000,000
----------------------------------------------------------------------------------------
Σ Bank Total           KES -1,240,079  KES -7,900,000,000  KES -7,901,240,079

Bank PBT (compute_pbt_from_cbs):  KES -7,901,240,079
Σ SBU PBT (sum_sbu_pbts):         KES -7,901,240,079
Delta:                            KES                  0   ✓
```

**Delta is exactly zero.** The identity holds. G254 locks it.

### `utils/pbt_computation.py` — extended

Six new functions:
- **`compute_pbt_by_sbu(cbs_dir, customer_segment_lookup=None) → Dict[str, PBTComponents]`** — the main entry
- **`sum_sbu_pbts(sbu_pbts) → PBTComponents`** — collapses per-SBU back to bank total (used by G254 to verify the identity)
- **`format_sbu_breakdown(sbu_pbts) → str`** — readable P&L
- `_load_segment_sbu_mapping()` — reads `data/segment_sbu_mapping.json`
- `_load_opex_by_sbu()` — reads `opex_data.json::by_sbu` with KES B → raw KES conversion
- `_load_customer_segment_lookup(cbs_dir)` — reads `customers.csv` for CIF → segment

### `data/segment_sbu_mapping.json` (NEW, Rule N1)

The codebase had **three concurrent segment naming conventions** (problem itself!):
1. `segment_config.json::_locked_codes` for production: AFFLUENT/CORE_MIDDLE/MASS/MICRO/SMALL/MEDIUM/CORPORATE
2. `VirtualBankCore.SegmentType` for dev/seed: RETAIL/HNW/PRIVATE_BANKING/SME/CORPORATE
3. `opex_data.json::by_sbu` display names: Retail Banking / Commercial Banking / Corporate Banking / Treasury / Digital/Agency

The mapping config unifies all three:
```json
{
  "segment_to_sbu": {
    "AFFLUENT": "Retail Banking", "CORE_MIDDLE": "Retail Banking",
    "MASS": "Retail Banking", "MICRO": "Retail Banking",
    "SMALL": "Commercial Banking", "MEDIUM": "Commercial Banking",
    "CORPORATE": "Corporate Banking",
    "RETAIL": "Retail Banking", "HNW": "Retail Banking",
    "PRIVATE_BANKING": "Retail Banking", "SME": "Commercial Banking"
  },
  "operational_sbus": ["Treasury", "Digital/Agency"]
}
```

Admin-editable. Tenants with different segment terminology adjust here; engine code untouched (Rule N1).

### Bridge writes `customers.csv` (NEW, companion to accounts.csv)

```csv
cif,full_name,segment,branch_code,rm_code
100000001,Sample Customer 001,RETAIL,001,RM_ECO_0001
100000002,Sample Customer 002,SME,002,RM_ECO_0014
...
```

This makes the SBU lookup CBS-native — `compute_pbt_by_sbu` doesn't need any external state, just the cbs_dir. In production with FLEXCUBE live mode, FLEXCUBE customer master can export to the same shape. The bridge's other guarantees (atomic write, deterministic ordering by CIF) extend to this file too.

### The Unallocated bucket — design decision

`opex_data.json` says bank.total_opex_kes_b = 7.9B, but Σ(by_sbu.opex_b) = 7.2B. The 700M gap is real OpEx that isn't attributed to any of the 5 named SBUs (head office, group services, central treasury overhead, etc.).

I deliberately did NOT proportionally redistribute the 700M across the named SBUs (would distort their P&Ls). Instead, an "Unallocated" bucket gets the gap and is shown explicitly. Three benefits:
1. The reconciliation identity holds **exactly** (not approximately)
2. The 700M is **visible** — surfaced as a real line, not silently buried
3. Tenants can later expand `opex_data::by_sbu` to include head office (etc.) explicitly; the Unallocated bucket will shrink as more OpEx becomes attributable

### `G254` — locks the identity

Verifies:
1. `compute_pbt_by_sbu` + `sum_sbu_pbts` + `format_sbu_breakdown` + helpers all present
2. `data/segment_sbu_mapping.json` exists with `segment_to_sbu` + `operational_sbus`
3. Bridge writes `customers.csv`
4. End-to-end probe: `Σ(SBU PBT)` is within KES 100 of `Bank PBT`
5. All expected SBUs in the result (Retail Banking, Commercial Banking, Corporate Banking, Treasury, Digital/Agency, Unallocated)

Cost: ~0.05s isolated.

## Files changed

| File | Change |
|---|---|
| `utils/pbt_computation.py` | +6 functions for SBU dimension; existing `compute_pbt_from_cbs` unchanged (additive) |
| `data/segment_sbu_mapping.json` | **NEW** — Rule N1 mapping config |
| `utils/virtual_bank_cbs_writer.py` | Writes new `customers.csv` (cif, full_name, segment, branch_code, rm_code) |
| `scripts/audit.py` | **NEW** `gate_sbu_reconciliation` (G254) |
| `scripts/verify_local_state.py` | Extended to 235 checks |
| `tests/integration/test_v10368_sbu_reconciliation.py` | **NEW** — 15 tests across 5 sections |
| `docs/Master_Prompt_v4.12.md` | **NEW** — lockstep bump from v4.11 |

## Verified outcome

| Metric | Value |
|---|---|
| **Σ(SBU PBT) - Bank PBT** | **KES 0 (exact)** — identity holds |
| Six SBU buckets returned | Retail, Commercial, Corporate, Treasury, Digital/Agency, Unallocated |
| Customers.csv rows | 100 (small seed); 3,206 production scale |
| OpEx gap absorbed by Unallocated | KES 700,000,000 |
| Audit gates | 253 → **254** (G254 locks identity) |
| Charter §2 (G249) | still PASS |
| PBT bank-level (G250) | still PASS |
| Bridge integrity (G245) | still PASS (extended schema preserved) |
| Reconciliation diagnostic (G253) | still informational (Engine B refactor → v10.372) |
| Page smoke | 123/123 + 0 static + 14/14 dynamic (preserved) |
| Tests | +15 in v10.368; **151 total across v10.358–v10.368** |
| Verifier | 226 → **235 checks** |
| Master prompt | v4.11 → **v4.12** — lockstep (13 consecutive batches) |
| G162 baseline | 4022 (**62 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **The identity holds within KES 100 tolerance, not zero.** On the seeded bank it happens to be exactly zero (Decimal arithmetic is precise here), but Decimal rounding can introduce tiny deltas at scale. G254 uses KES 100 as the threshold — generous but appropriate for a bank P&L.

2. **Treasury and Digital/Agency show -OpEx PBT** because there's no customer-attributable income for them in CBS. In production, treasury revenue comes from a separate GL (interbank trading, FX desk, securities). Digital/Agency revenue comes from channel fees that aren't yet broken out per-channel in accounts.csv. The negative PBT is structurally correct given current data; future batch can add treasury/channel income feeds.

3. **The 700M Unallocated OpEx is a real number, not noise.** It's the gap between the bank's total operating cost (7.9B) and what `opex_data::by_sbu` attributes (7.2B). In production this would be head office costs, group services, regulatory levies, etc. Showing it explicitly is the right call — silently redistributing would mislead.

4. **Retail Banking gets all of: AFFLUENT, CORE_MIDDLE, MASS, MICRO, RETAIL, HNW, PRIVATE_BANKING.** That bundles HNW + Private Banking with Mass Market under "Retail" because that's how `opex_data::by_sbu` is structured (no separate Private Banking SBU). Tenants who want separate Private Banking can add it to `opex_data::by_sbu` AND update the mapping — both files are Rule N1 admin-editable.

5. **MICRO businesses go to Retail Banking.** In Kenyan banking practice (and most emerging markets) microenterprises bank with retail because their needs are similar (transactional, small balances). Tenants who treat MICRO as Commercial can flip the mapping line.

6. **The bridge now writes 7 files instead of 6.** customers.csv is the new one. Bridge atomic-write + deterministic-ordering guarantees extend to it. Pattern T (cumulative zip copies all data files) automatically picks it up because the cbs_data directory pattern was already preserved.

7. **`compute_pbt_from_cbs` is unchanged.** The SBU dimension is purely additive. All existing callers (compute_bank_aggregates, MD's BSC) keep working byte-identically. No regression risk on bank-level PBT.

8. **Engine B (sbu_pnl_rollup) still walks customer_intelligence.** It doesn't yet consume from compute_pbt_by_sbu. So G253 reconciliation diagnostic still shows the same 90% divergence (it compares pbt_computation vs sbu_pnl_rollup at the BANK level, where they still differ for the reasons documented). Engine B refactor is v10.372, the last batch in the arc.

9. **G254 is structurally strict.** It requires the identity within KES 100 — much tighter than the 5% target for G253 in v10.370. The reason: G254 measures something the engine CONTROLS (rolled up from same data); G253 measures something it doesn't (different data sources entirely until v10.372 ships).

10. **`format_sbu_breakdown` doesn't show NII / fee_income separately.** It's a high-level summary (OpIncome, OpEx, PBT). For full drill-down, callers use the `PBTComponents` per SBU directly (each has the full 19-field structure from v10.364).

11. **Rule N2 held.** v10.368 is single-purpose: add SBU dimension. Did not touch per-branch (v10.369), per-RM (v10.370), bank_targets schema (v10.371), or Engine B (v10.372). Each is its own batch.

12. **The v10.364 lesson held.** `pbt_computation` still has zero upward `utils.*` imports — even with the new functions, it only reads from data/ files via stdlib (json, csv). G250's structural check continues to pass.

13. **Q2 (proxy revenue sunset) wasn't addressed in v10.368.** That comes in v10.372 (Engine B refactor). Engine B's proxy mode is documented as deprecated then but kept for backward compatibility one more batch.

14. **Q4 (proposition visibility) wasn't addressed in v10.368.** It's a UI question, not a data question. The data architecture (Rule 6 in sbu_pnl_rollup.reconcile_to_bank) is correct as-is. The MD-facing UI work belongs in v10.373+ (after the unification is complete).

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10368_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 235 CHECKS PASSED**
5. **See the SBU breakdown:**
   ```
   python -c "
   import tempfile
   from pathlib import Path
   from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
   from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
   from utils.pbt_computation import compute_pbt_by_sbu, sum_sbu_pbts, format_sbu_breakdown, compute_pbt_from_cbs
   bank, _ = seed_virtual_bank(config=SeedConfig.small())
   with tempfile.TemporaryDirectory() as td:
       persist_bank_to_cbs(bank, output_dir=Path(td))
       sbu_pbts = compute_pbt_by_sbu(Path(td))
       print(format_sbu_breakdown(sbu_pbts))
       bank_pbt = compute_pbt_from_cbs(Path(td))
       sbu_total = sum_sbu_pbts(sbu_pbts)
       print()
       print(f'Identity check: delta = {float(bank_pbt.pbt - sbu_total.pbt):,.0f}')
   "
   ```
6. Read `docs\Master_Prompt_v4.12.md` — thirteenth consecutive lockstep batch.
7. (Optional, takes >5min) Audit → expect **254/254 PASS**

## v10.369+ roadmap (the unification arc continues)

| Batch | Concern | Closes |
|---|---|---|
| **v10.369** | `branch_pbt_allocator.py` — admin-configurable allocation driver (FTE-weighted default) | Σ(Branch PBT) = Bank PBT — G255; G253 ratchets to <5% |
| **v10.370** | `rm_profitability.py` refactored to consume canonical | Σ(RM PBT) = Bank PBT — G256 |
| **v10.371** | Multi-level `bank_targets.json` schema | Top-down + bottom-up at every level; G253 → CONVERGED |
| **v10.372** | Engine B (sbu_pnl_rollup) refactor to consume canonical | Eliminates the parallel-engines structural debt |
| **v10.373+** | UI surfacing in MD dashboard, Finance hub, branch ranking | Visible drill-downs across the platform |
| **v10.4XX+** | React executive frontend (Standard #9) | Next major arc |

**The SBU dimension is done. v10.369 is per-branch. Same pattern — allocator + identity + gate.**

Want me to proceed?
