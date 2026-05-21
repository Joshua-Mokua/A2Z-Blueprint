# Consolidated Cleanup Sweep + Batch Plan

**Date:** 2026-05-13
**Scope:** All pending cleanup items + backlog reconciliation before v10.403 starts
**Method:** 14 sweeps across data files, tests, backups, designs, weights

---

## Cleanup items found — 14 distinct issues across 4 categories

### 🔴 Category A — Data pollution (critical, blocks correct cascade)

| # | Issue | Detail |
|---|---|---|
| **A1** | 10 synthetic EXEC-* chiefs still in users.json | exec_cfo_001, exec_cco_001, exec_cio_001, exec_chro_001, exec_cia_001, exec_coo_001, exec_cro_001, exec_crso_001, exec_ccmp_001, exec_ccmo_001 — all have staff_codes starting "EXEC-" |
| **A2** | 112 phantom cascade entries from synthetic chiefs (as senders) | These chiefs cascade to non-existent reports |
| **A3** | 560 cascade allocations TO synthetic chiefs | They receive cascade from real MD |
| **A4** | 56 cascade allocations to ADMIN001 | Joshua's monitoring account receiving business KPI cascade |
| **A5** | 11 test entries in canonical_change_log.json | test_user/deep_test entries from this session |

### 🟡 Category B — KPI library duplicates (correctness)

| # | Issue | Detail |
|---|---|---|
| **B1** | 'New Accounts Opened' has both `K006` AND `NEW_ACCOUNTS` ids | duplicate library entry |
| **B2** | 'Digital Channel Adoption (%)' has both `K024` AND `K069` ids | duplicate library entry |
| **B3** | 'Collateral Review Completion (%)' has both `K028` AND `K048` ids | duplicate library entry |
| **B4** | 'Net Interest Margin' has both `NET_INTEREST_MARGIN` AND `NIM` ids | duplicate library entry |

### 🟡 Category C — Role weight integrity (BSC scoring accuracy)

| # | Issue | Detail |
|---|---|---|
| **C-WT1** | 225 of 227 roles have weight sums ≠ 1.0 | Only "Senior Manager Credit Analysis" + "Risk Manager" sum correctly |
| **C-WT2** | Most roles are UNDER-weighted (213 < 1.0) | E.g., Core Banking Support Officer sums to 0.10 (10%) |
| **C-WT3** | 12 roles are OVER-weighted (sum > 1.0) | Branch Manager, Branch Operations Manager, etc. |
| **C-WT4** | Effect: BSC scoring is currently scaled wrong | If a role's weights sum to 0.10, max possible BSC score = 10% (looks like everyone is failing) |

### 🟡 Category D — Housekeeping (low risk)

| # | Issue | Detail |
|---|---|---|
| **D1** | Stale test: `test_v10397_total_unique_codes_increased` asserts 1449 | Actual = 1448 post-v10.399 |
| **D2** | 122 MB of overlapping rescue arc backups (v10.396-v10.402) | Each ~25 MB; consolidate or archive |
| **D3** | 11 retired-but-present test functions across 3 files | Clutter; could be physically removed |
| **D4** | 8 archived uppercase bank_target entries with conflicting values | Need Joshua decision on which values are authoritative |

### ⚠️ Category E — Pre-cascade design issues from earlier review

| # | Issue | Detail |
|---|---|---|
| **E-C1** | Regenerator overwrites manual manager allocations | CRITICAL — needs scaffolding mode |
| **E-C2** | No per-manager buffer | CRITICAL — your core design intent |
| **E-C3** | MD's bank-target buffer doesn't flow to cascade | CRITICAL |
| **E-C5** | Admin role receives business KPI cascade | Same as A4 (will be fixed by A4) |
| **E-C6** | Manager doesn't see "remaining to allocate" | UX gap |
| **E-C7** | No retain-portion capability | Design gap |
| **E-C8** | Verify Fixed KPIs hidden from manager forms | UX verify |
| **E-C9** | No layer ancestry display | UX gap |

### ⚠️ Category F — Pending Joshua decisions (no code change yet)

| # | Issue | Detail |
|---|---|---|
| **F1** | Pillar weights: 68/14/6/12 vs Kaplan-Norton 40/25/25/10 | Your call |
| **F2** | Bank target buffer semantics (informational vs operational) | Your Q1 |
| **F3** | Manager retain-portion allowed or 100% must cascade | Your Q2 |
| **F4** | Regenerate behavior (scaffolding/full/ask) | Your Q3 |
| **F5** | Fixed KPI display (hide/lock/grey) | Your Q4 |
| **F6** | Archived uppercase bank_target values (8 entries) | Old values stored, awaiting reconciliation |

---

## Batch plan v10.403 onwards

Sequenced so each batch is **safe, isolated, testable, and reversible**:

### v10.403 — Data cleanup (NO design changes, fully safe)
**Touches**: data files only. No engine logic, no UI changes.

1. **A1** Delete 10 EXEC-* synthetic chiefs from users.json
2. **A4** + **E-C5** Add Admin role to cascade-excluded list (in regenerator)
3. **A5** Clean test entries from canonical_change_log.json
4. **A2 + A3** Re-regenerate cascade → phantom entries auto-disappear
5. **D1** Retire stale v10.397 staff_code test
6. **B1-B4** Mark library duplicates with `_v10403_alias_of` field (don't delete yet — let kpi_library refactor happen separately)

**Expected result**: MD's cascade shows 10 chiefs (not 20); cascade size drops accordingly; engine still 0/0/0/0.

### v10.404 — Regenerator preserves manual allocations (CRITICAL bug fix)
**Touches**: `utils/cascade_regenerator.py` + Admin UI Regenerate button.

1. **E-C1** Add `scaffolding_mode=True` parameter to `regenerate_target_cascade`
2. Default mode: only add cascade entries that don't already exist; preserve manual
3. Force-rebuild mode: current behavior (use only when admin explicitly chooses)
4. Admin UI: "Regenerate Cascade" button asks "Preserve manual allocations? [Yes/No]"
5. Tests verify manual allocation survives admin regen

### v10.405 — Per-manager buffer + bank-target buffer propagation (your core design)
**Touches**: schema + UI + regenerator.

1. **E-C2** Add `buffer_pct` and `stretch_target` fields to cascade entry schema
2. UI: 'Set team targets' tab gets buffer input per KPI
3. **E-C3** Regenerator: respect per-layer buffer when present; fall back to MD's bank-target buffer; fall back to raw target
4. BSC: read most-local-layer stretch target for scoring
5. Tests for buffer propagation through multi-layer cascade

### v10.406 — Manager retain + remaining indicator + UI polish
**Touches**: UI + validation.

1. **E-C7** Add `retained_amount` field
2. **E-C6** Live "remaining to allocate = X" indicator in 'Set team targets'
3. Validation: retained + sum(allocations) ≤ total_received

### v10.407 — Role weight renormalization (BSC accuracy)
**Touches**: kpi_library.json.

1. **C-WT1-WT4** For each role with weight sum ≠ 1.0, renormalize proportionally
2. Preserve relative weights; just scale sum to 1.0
3. Add validator: assert all role weight sums = 1.0 ± 0.01
4. Admin UI shows weight sum for transparency

### v10.408 — UI polish + ancestry display
**Touches**: cascade page UI.

1. **E-C8** Verify Fixed KPIs are HIDDEN (not shown locked) in manager allocation forms
2. **E-C9** Add full ancestry display in Cascade Tree tab
3. **F5** Apply Joshua's preference once decided

### v10.409 — KPI library deduplication (B1-B4 follow-up)
**Touches**: kpi_library.json.

1. Pick canonical id for each duplicate (B1-B4)
2. Migrate references in role_kpis + bank_targets + fixed_kpis
3. Archive (don't delete) duplicate library entries

### v10.410 — Backup retention cleanup (housekeeping)
**Touches**: data/_v10*_backups/.

1. **D2** Archive old rescue arc backups (v10.396-v10.401)
2. Keep v10.402 latest as restore point
3. Document restore procedure

### Future / pending Joshua decisions
- **F1** Pillar weights: when Joshua confirms 68/14/6/12 or switch to 40/25/25/10
- **F2-F5** Design questions baked into v10.404-v10.408 once answered
- **F6** Reconcile archived bank target values

---

## Recommended execution order

Joshua's priority lens — clean data first, then critical bug fixes, then design features:

```
v10.403  [SAFE]  Data cleanup (synthetic chiefs, Admin exclusion, stale test)
   ↓
v10.404  [BUG]   Regenerator preserves manual allocations
   ↓
v10.405  [FEAT]  Per-manager buffer (your core design)
   ↓
v10.406  [FEAT]  Manager retain + remaining indicator
   ↓
v10.407  [DATA]  Role weight renormalization
   ↓
v10.408  [UX]    UI polish
   ↓
v10.409  [DATA]  KPI library dedup
   ↓
v10.410  [HOUSE] Backup retention
```

---

## Stats at v10.402 baseline

| Metric | Value |
|---|---|
| Audit gates | 288 |
| Integration tests | ~400 |
| Verifier checks | 559 |
| Cascade entries | 24,192 |
| Engine state | 0/0/0/0 ✓ |
| users.json | 1448 entries (10 to be removed in v10.403) |
| Real chiefs | 10 (CRBO, CCO, CFO, Chief Credit, CRO, CIO, COO, CHRO, Co-Sec/Legal, GM Banc) |
| Synthetic chiefs to remove | 10 (EXEC-*) |
| Roles with correct weight sums | 2 / 227 |
| Bank target archived entries | 8 (decision pending) |

---

## Question for Joshua before starting v10.403

v10.403 is purely data cleanup — safe to run independently. Specifically:

1. Delete 10 synthetic chiefs from users.json → `data/_v10403_backups/`
2. Exclude Admin role from cascade allocations (regenerator filter)
3. Clean 11 test entries from canonical_change_log.json
4. Fix 1 stale test (v10.397 staff_code)
5. Re-regenerate cascade (will drop from 24,192 → ~21,500 entries)
6. Engine should still be 0/0/0/0

**Ok to proceed with v10.403?** If yes, say "continue" and I'll ship it. If you want any of the items above swapped/skipped, tell me which.

Also: for **v10.405** (per-manager buffer — your CRITICAL design intent), I'll need your answers on **F2-F5** (buffer semantics, retain-portion, regenerate behavior, fixed KPI display). You can answer those after v10.403/v10.404 land if easier.
