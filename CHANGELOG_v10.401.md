# Changelog — v10.401 Period Harmonization (TC38 Resolved)

**Date:** 2026-05-13
**Phase:** Phase C2 cleanup batch — Target Cascade Rescue arc
**Audit:** G287 added
**Tests:** 11/11 PASSED in `test_v10401_period_harmonization.py`
**Verifier:** 552/552 checks pass
**G162 baseline:** 4022 (94 consecutive zero-drift batches)
**Master prompt:** v4.43 → v4.44 (lockstep — 45 consecutive batches)

---

## Problem (TC38)

Periods inconsistent across the three core data files:

| File | Period scheme |
|---|---|
| `fixed_kpis.json` | Quarterly (`2026-Q1`, `2026-Q2`, ...) |
| `bank_targets.json` | Annual (`PBT\|2026`) |
| `target_cascade.json` | Annual (`300001\|PBT\|2026`) |

When the annual cascade asked "is X fixed for 2026?", the regenerator used a "union all quarters" workaround. This worked when quarters agreed but had no explicit annual override capability — a KPI fixed in Q1 only would be treated as fixed for the whole year.

Per Joshua's directive earlier: "Fixed KPIs are the reserve of MD ... they might change" — implies quarterly flexibility is desired. But annual cascade needs a coherent view.

## Solution

Built `utils/period_harmonizer.py` leaf module that supports BOTH quarterly granularity AND explicit annual override:

```
If annual key '2026' exists in fixed_kpis → use it directly (authoritative)
Else → fall back to union of '2026-Q*' quarters (legacy behavior)
```

This is backward-compatible: existing quarterly-only data continues to work. New explicit annual keys give MD/admin a faster path when the annual list doesn't vary by quarter.

## What v10.401 did

### Component 1: `utils/period_harmonizer.py` (~250 LOC, leaf, AST-verified, 5 self-tests)

| Function | Purpose |
|---|---|
| `get_fixed_kpis_for_period(period)` | Annual key wins, falls back to quarter union |
| `get_quarters_for_year(year)` | `{Q1, Q2, Q3, Q4} → set_of_kpis` per quarter |
| `promote_quarters_to_annual(year, who, reason)` | Derive annual key from quarter union |
| `validate_period_consistency(year)` | Check annual vs union for divergence |
| `set_annual_fixed_kpis(year, kpis, who, reason)` | Set explicit annual override |
| `list_periods()` | List all periods grouped by type |

### Component 2: Regenerator integration

Updated `utils/cascade_regenerator.py::_get_fixed_kpi_set` to prefer annual key when present, fall back to quarterly union otherwise. Backward-compatible — no breaking change.

### Component 3: Seed annual 2025 + 2026 keys

Used `promote_quarters_to_annual` to derive authoritative annual lists from the existing quarterly entries:
- **2026**: 16 fixed KPIs (Q1+Q2 already consistent — same list)
- **2025**: 16 fixed KPIs (Q3+Q4 already consistent — same list)

Now production admin can edit annual directly OR continue per-quarter; both modes work.

## Verified outcome

| Metric | v10.400 | v10.401 |
|---|---|---|
| Cycles | 0 | **0** ✓ |
| Cross-branch | 0 | **0** ✓ |
| Multi-sender | 0 | **0** ✓ |
| Rep_critical | 0 | **0** ✓ |
| Cascade entries | 25,488 | **25,488** ✓ |
| Audit gates | 286 → **287** | |
| Tests | 270 → **281** | |
| Verifier | 547 → **552** | |
| Master prompt lockstep | **45/45** | |
| G162 baseline | 4022 (**94 consecutive zero-drift**) | |

## 10 honest acknowledgements

1. **TC38 resolved.** Period harmonization now explicit, with admin override available.

2. **Backward-compatible.** Existing quarterly-only data continues to work. Annual key is opt-in.

3. **Seed step done.** Annual 2025 and 2026 keys now in fixed_kpis.json; quarters preserved alongside.

4. **5-function helper module.** Compact, focused, leaf-pure.

5. **Engine state preserved.** Adding annual keys didn't change which KPIs are fixed (since quarters were already consistent for 2026).

6. **Quarters were already consistent.** All 2026 quarters had the same 16 KPIs; same for 2025. The "union" workaround was correct in practice — v10.401 just made it explicit and editable.

7. **Validator surfaces divergence.** If admin sets annual=A and quarters=B, `validate_period_consistency` flags it.

8. **Promote function** lets admin derive annual from quarters in one call.

9. **Backup preserved.** `data/_v10401_backups/fixed_kpis.json.before`.

10. **45 consecutive lockstep batches.** No drift between master prompt and code.

## Phase C2 progress

| Batch | Concern | Status |
|---|---|---|
| ~~v10.391-v10.400~~ | Diagnosis through admin UI | ✅ |
| ~~**v10.401**~~ | **Period harmonization (TC38)** | ✅ **DONE** |
| v10.402 | NPL naming consolidation (TC39) | next |

## On your end

1. Close Streamlit
2. Extract `a2z_v10401_patch.zip` flat on top of v10.400 state
3. Run `python scripts\verify_local_state.py` → expect **552/552**
4. Engine check: `python utils\cascade_structure_engine.py` → 0/0/0/0
5. Check `data\fixed_kpis.json` — should now have `"2025"`, `"2025-Q3"`, `"2025-Q4"`, `"2026"`, `"2026-Q1"`, `"2026-Q2"` keys
6. Tell me **"continue"** → v10.402 = NPL naming consolidation (TC39 — `NPL Ratio` human name vs `NPL_RATIO` uppercase)

## What v10.402 will do

Resolve TC39 — the same financial concept has two naming representations:
- `NPL Ratio` (human-readable, lower-case word, used in BSC display)
- `NPL_RATIO` (uppercase, machine-style, used in fixed_kpis list and `K-prefixed` IDs)

This causes:
- Confusion in admin UI (which one to edit?)
- Risk of one being cascaded and the other being fixed
- Cross-system inconsistency

Resolution: canonical KPI ID scheme + alias resolver (v10.380 pattern). Map both forms to a single canonical record; everywhere that reads either gets the same data.

Continue?
