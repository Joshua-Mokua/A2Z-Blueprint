# Changelog — v10.371 Multi-Level bank_targets Schema (Top-Down Atomic)

**Date:** 2026-05-13
**Phase:** 4 (fifty-sixth arc — fourth unification step; the targets side gets the same atomic treatment as actuals)
**Audit:** G258 added (locks Σ(child targets) = bank target within 0.1%)
**Tests:** 18/18 PASSED in `test_v10371_target_hierarchy.py`; 185 prior tests unchanged = **203 total**
**Page smoke:** 123/123 PASS + 0 static findings + 14/14 dynamic renders pass
**Verifier:** 269/269 checks pass on a clean extract
**G162 baseline:** 4022 (65 consecutive zero-drift batches)
**Master prompt:** v4.14 → v4.15 (lockstep — sixteenth consecutive batch)

---

## Your ask

> "continue"

Autonomous continuation per your standing instruction. v10.371 closes the top-down half of the unification arc that v10.368-v10.370 closed bottom-up.

## The complete reconciliation picture (now bidirectional)

```
                                    Bank PBT
                                       │
                                       │    ┌─ TARGETS ───────────────────┐
                                       │    │  PBT|bank|all|2026          │
                                       │    │  PBT|sbu|<name>|2026        │
                                       │    │  PBT|branch|<code>|2026     │
                                       │    │  PBT|staff|<code>|2026      │
                                       │    │  PBT|customer|<CIF>|2026    │
                                       │    │  Σ(child) == parent (G258)  │ NEW
                                       │    └──────────────────────────────┘
   ┌─ ACTUALS ─────────────────────────┤
   │                                   │    Σ checked at every level
   │  bank PBT (G250, v10.364)          │
   │  Σ SBU PBT  == bank (G254, v10.368)│
   │  Σ Branch PBT == bank (G255, v10.369)│
   │  Σ Customer PBT == bank (G256, v10.370) [ATOMIC]
   │  Σ Staff PBT == bank (G257, v10.370)│
   └──────────────────────────────────┘
```

The MD's "Is the bank on track?" answer is now derivable at every level: SBU, branch, RM, individual customer. Actuals atomic since v10.370; targets atomic since v10.371.

## What v10.371 delivered

### `utils/bank_targets_schema.py` — NEW (~470 LOC, 16 self-tests)

Pure schema utility. Zero imports from `utils.*` (no upward, no downward — completely standalone parser). Self-test uses synthetic dicts. Single responsibility: parse, validate, and migrate bank_targets keys.

**Exports:**

| Function | Purpose |
|---|---|
| `parse_target_key(key)` | Returns `TargetKey(metric, level, entity, year)` or None |
| `compose_target_key(metric, level, entity, year)` | Canonical 4-segment key string |
| `migrate_legacy_targets(raw)` | Adds bank\|all aliases for legacy 2-segment keys |
| `get_target(targets, metric, level, entity, year)` | Read with legacy fallback for bank\|all |
| `set_target(targets, metric, level, entity, year, value)` | Always writes canonical 4-segment |
| `list_targets_at_level(targets, metric, level, year)` | Returns `[(entity, record), ...]` at level |
| `sum_children_at_level(targets, metric, level, year)` | Decimal sum of target values |
| `validate_target_hierarchy(targets, metric, year, tolerance_pct)` | List of violations (empty = pass) |
| `load_bank_targets(path, migrate=True)` | Reads + optionally migrates |
| `save_bank_targets(targets, path, strip_aliases=True)` | Writes back without alias duplication |

### Schema

**Legacy (still works exactly as before):**
```
"PBT|2026":                {"target": 650000000000, "buffer_pct": 0}
"Total NFI|2026":          {"target": 50000000000,  "buffer_pct": 0}
```

**New (admin can mix legacy + new freely):**
```
"PBT|bank|all|2026":              {"target": 650000000000, "buffer_pct": 0}
"PBT|sbu|Retail Banking|2026":    {"target": 200000000000, "buffer_pct": 0}
"PBT|sbu|Commercial Banking|2026": {"target": 300000000000, "buffer_pct": 0}
"PBT|sbu|Corporate Banking|2026": {"target": 150000000000, "buffer_pct": 0}
"PBT|branch|BR001|2026":          {"target": 10000000000,  "buffer_pct": 0}
"PBT|staff|300046|2026":          {"target": 50000000,     "buffer_pct": 0}
"PBT|customer|1000000088|2026":   {"target": 2000000,      "buffer_pct": 0}  # rare
```

### Migration behavior

When `load_bank_targets(migrate=True)` reads the file:

| File contains | Memory exposes |
|---|---|
| Only `PBT\|2026` (legacy) | `PBT\|2026` AND `PBT\|bank\|all\|2026` (same dict — alias) |
| Only `PBT\|bank\|all\|2026` (new) | Just that key |
| Both | Both (admin decides; both point at same canonical record) |

The file ON DISK is never modified by load. Admins write whichever format they prefer; the new schema is purely additive.

### Hierarchy identity (G258)

For any `(metric, year)`:

```
Σ(targets where level=L and entity matches metric/year) 
    == bank|all target for that metric/year
                              ± tolerance_pct  (default 0.1%)
```

Checked across all child levels: `sbu`, `branch`, `staff`, `customer`. **Sparse OK** — only levels with populated targets are checked. Admins populate progressively.

Production `bank_targets.json` validates clean (no child targets populated yet — sparse-OK behavior gives empty violations list).

### Override flag

```
"_force_unbalanced_targets": true
```

At the top of `bank_targets.json` returns informational "validation skipped" notice rather than failing. Used for admin edge cases (e.g., draft targets where some children haven't been set yet).

### Tests — 18/18 across 5 sections

**Section 1 (module):** module surface, self_test passes, levels constants defined

**Section 2 (parsing):** legacy 2-segment parses as bank|all, new 4-segment parses, invalid keys return None (empty, underscore-prefixed metadata, 1-segment, 3-segment), migration creates aliases without modifying original

**Section 3 (THE HIERARCHY IDENTITY):** balanced passes, unbalanced fails with descriptive message, tolerance configurable (0.1% line case), sparse OK, override flag short-circuits

**Section 4 (live behavior):** production bank_targets.json validates clean, legacy bank|all read works, save strips alias to avoid double-writing

**Section 5 (gates + regression):** G258 passes, Charter §2 still passes, all four v10.370 actuals identities still hold

## Files changed

| File | Change |
|---|---|
| `utils/bank_targets_schema.py` | **NEW** (~470 LOC, 16 self-tests) |
| `scripts/audit.py` | **NEW** `gate_target_hierarchy` (G258) |
| `scripts/verify_local_state.py` | Extended to 269 checks |
| `tests/integration/test_v10371_target_hierarchy.py` | **NEW** — 18 tests across 5 sections |
| `docs/Master_Prompt_v4.15.md` | **NEW** — lockstep bump from v4.14 |

**Zero changes to `bank_targets.json`.** Production file stays exactly as Joshua's admins last wrote it. The schema engine reads it, migrates in-memory, validates against any populated children. New format is opt-in and can be mixed freely with legacy.

## Verified outcome

| Metric | Value |
|---|---|
| Legacy 2-segment keys preserved | 150/150 (100%) |
| Aliases added on load | 150 (bank\|all for every legacy) |
| Validation on production data | **CLEAN** (sparse-OK, no children yet populated) |
| Audit gates | 257 → **258** (G258 locks hierarchy identity) |
| Charter §2 (G249) | still PASS |
| All v10.370 actuals identities (G250-G257) | still PASS |
| Page smoke | 123/123 + 0 static + 14/14 dynamic |
| Tests | +18 in v10.371; **203 total across v10.358–v10.371** |
| Verifier | 256 → **269 checks** |
| Master prompt | v4.14 → **v4.15** — lockstep (16 consecutive batches) |
| G162 baseline | 4022 (**65 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **No child targets populated in production yet.** v10.371 ships the engine, not the data. Admins use the existing target-management UI to populate per-SBU/branch/staff targets as they're ready. The validation passes by default (sparse-OK) until populated, at which point it enforces.

2. **0.1% (10bp) default tolerance is generous.** It allows for the kinds of rounding admins do when allocating ("let's give Retail KES 200B and Commercial KES 300B" without doing exact math). Admins can tighten to 0.01% if they want strict reconciliation. They can also widen if SBU/branch targets are aspirational and exceed bank total deliberately.

3. **SBU, Branch, Staff, and Customer are parallel views from Bank, not hierarchical to each other.** A customer belongs to both an SBU AND a branch. So we check `Σ(sbu) == bank` AND `Σ(branch) == bank` AND `Σ(staff) == bank` AND `Σ(customer) == bank` separately. We do NOT check `Σ(staff) == Σ(branch)` because both must equal bank, which transitively makes them equal.

4. **`_force_unbalanced_targets=True` is a global escape hatch** — applies to the entire targets dict, not per-metric. If an admin needs to ship unbalanced targets for just one metric while keeping others enforced, they need to either fix the others first or use the override and accept that everything bypasses. Per-metric override would be a future refinement; not critical for v10.371.

5. **The migration alias trick (legacy `PBT|2026` becomes `PBT|bank|all|2026` in memory)** means consumers should call `load_bank_targets()` rather than reading the file directly. Future cleanup: refactor MD BSC / Link 7 binding to call this. Until then, both keys work (they point at the same dict record).

6. **`save_bank_targets(strip_aliases=True)`** drops the canonical 4-segment alias when the legacy 2-segment exists, so save→load round-trips don't bloat the file. If an admin EXPLICITLY writes both legacy and new 4-segment for bank|all (different values), the legacy wins on save by default. Pass `strip_aliases=False` to preserve both verbatim.

7. **G258 is fast (~0.05s)** — pure schema reasoning, no I/O beyond reading bank_targets.json once. Cheaper than G256/G257 (which seed and persist a bank).

8. **Customer-level targets (e.g. `PBT|customer|1000000088|2026`)** are technically supported but operationally rare. Real banks set per-customer targets only for top tier (HNW, large corporates). The schema doesn't enforce sparseness — admin chooses.

9. **G253 still informational.** v10.371 didn't ratchet it because the divergence is between Engine A and Engine B actuals, not targets. v10.372 (Engine B refactor) is where G253 becomes CONVERGED.

10. **bank_targets.json file size implications.** With 35 KPIs across the new dimensions, 94 branches × 35 metrics × 1 year = 3,290 branch-level keys. Plus 419 RMs × ~5 critical metrics = ~2,100 staff keys. Plus 6 SBUs × 35 metrics = 210 SBU keys. Total ~6,000 keys vs current 150 — manageable JSON file, but consider sharding by year if it grows to multiple horizons (2025/2026/2027).

11. **Rule N2 held**: single batch, one concern (schema extension). Did not touch consumers (MD BSC, Link 7 binding) — those reference the schema via existing `bank_targets.json` reads and still work. Cleanup batch (v10.374+) can migrate them to `load_bank_targets()` for the alias support.

12. **The v10.364 module purity lesson held**: `bank_targets_schema` has zero `utils.*` imports. It's pure Python + JSON. Self-test uses synthetic dicts only. G128 stays green.

13. **No new data file added** (unlike v10.368 segment_sbu_mapping or v10.369 branch_allocation_rules). The schema engine reads existing bank_targets.json with extended interpretation; no new config file needed.

14. **Test coverage for save_bank_targets**: the test verifies `strip_aliases=True` behavior but doesn't exercise `strip_aliases=False`. Edge case is documented in the code but tested only via the self_test in the module (not in the integration test file). Not critical — the round-trip behavior is straightforward.

15. **Joshua's three deferred decisions from v10.370 wrap-up are partially resolved:**
    - ✓ Schema shape: `<metric>|<level>|<entity>|<year>` adopted
    - ✓ Validation: enforce by default (returns violations); admin override via `_force_unbalanced_targets` flag
    - ⏳ Role definitions (portfolio-owning vs service staff) — deferred to v10.373 UI batch as planned

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10371_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 269 CHECKS PASSED**
5. **Inspect schema migration on your real bank_targets.json:**
   ```
   python -c "
   from utils.bank_targets_schema import (
       load_bank_targets, validate_target_hierarchy, list_targets_at_level,
       LEVEL_BANK, LEVEL_SBU, BANK_ENTITY_ALL, get_target,
   )
   targets = load_bank_targets()
   print(f'Total keys after migration: {len(targets)}')
   rec = get_target(targets, 'PBT', LEVEL_BANK, BANK_ENTITY_ALL, '2026')
   print(f'Bank PBT 2026: KES {rec[\"target\"]:,.0f}')
   for level in ('sbu', 'branch', 'staff', 'customer'):
       n = len(list_targets_at_level(targets, 'PBT', level, '2026'))
       print(f'  PBT|{level} entries: {n}')
   v = validate_target_hierarchy(targets, 'PBT', '2026')
   print(f'Validation violations: {len(v)} ({\"clean\" if not v else v[0]})')
   "
   ```
6. **Try populating SBU-level targets to see the engine in action:**
   ```
   python -c "
   from utils.bank_targets_schema import (
       load_bank_targets, set_target, validate_target_hierarchy,
       sum_children_at_level, LEVEL_SBU,
   )
   from decimal import Decimal
   targets = load_bank_targets()
   # Simulated: split bank PBT 650B across SBUs
   set_target(targets, 'PBT', LEVEL_SBU, 'Retail Banking', '2026', {'target': 200000000000})
   set_target(targets, 'PBT', LEVEL_SBU, 'Commercial Banking', '2026', {'target': 300000000000})
   set_target(targets, 'PBT', LEVEL_SBU, 'Corporate Banking', '2026', {'target': 150000000000})
   total = sum_children_at_level(targets, 'PBT', LEVEL_SBU, '2026')
   print(f'Σ(SBU PBT targets) = KES {float(total):,.0f}')
   print(f'Bank PBT target:    KES 650,000,000,000')
   v = validate_target_hierarchy(targets, 'PBT', '2026')
   print(f'Violations: {len(v)}')
   "
   ```
7. Read `docs\Master_Prompt_v4.15.md` — sixteenth consecutive lockstep batch.
8. (Optional, takes >5min) Audit → expect **258/258 PASS**

## v10.372 next — Engine B refactor (the arc closes)

v10.372 refactors `sbu_pnl_rollup.bank_total_pnl` to optionally consume from `compute_pbt_by_customer` (the v10.370 atomic engine). Once that's in, Engine A and Engine B produce the same numbers — and **G253 finally ratchets to CONVERGED (<1%)**.

After v10.372:
- Bottom-up: per-customer atomic, Σ to bank (G250, G254-G257) ✓
- Top-down: per-customer targets atomic, Σ to bank (G258) ✓
- Engine convergence: A and B agree (G253 ratchet) ⏳ v10.372
- UI surfacing: dimensions visible in MD dashboard / Finance hub ⏳ v10.374+

**Four of five unification batches done. One architectural batch to go; then UX surfacing.**

Want me to proceed with v10.372?
