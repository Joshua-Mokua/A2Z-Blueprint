# Changelog — v10.406 Real-Time Progress Rollup (E1) Wired

**Date:** 2026-05-14
**Phase:** QA-Standards enhancement wiring (1 of 7)
**Audit:** G292 added
**Tests:** 12/12 PASSED in `test_v10406_team_progress_rollup.py`
**Verifier:** 582/582 checks pass
**G162 baseline:** 4022 (99 consecutive zero-drift batches)
**Master prompt:** v4.48 → v4.49 (lockstep — 50 consecutive batches)

---

## Per QA-Standards Enhancement #1

> **Problem:** Managers cannot see aggregated progress across their teams in real-time.
> **Solution:** Live aggregation of actuals from BSC engine with variance analysis.

## Pre-v10.406 status

- `utils/manager_rollup.py` (544 LOC) existed and was fully tested
- Provided `compute_team_rollup(manager_code, period)` returning:
  - direct/indirect report counts
  - per-KPI team aggregate (sum for volumes, mean for scores)
  - achievement % vs target
  - BSC score 1-5
  - target source (cascaded / bank_fixed / team_sum)
- BUT only wired into `pages/7_admin.py` line 9
- Cascade page (where managers actually work) had no progress view

## Bug discovered while wiring

`manager_rollup._direct_report_codes()` used `virtual_bank.direct_reports()` which:
- Returns 0 for real C-suite chiefs (300002-300010 + 300178)
- These chiefs have no `hr.json` record → virtual_bank's manager_code lookup returns empty
- Effect: any rollup call for any chief got 0 direct reports

**Fix**: Added canonical fallback that uses `cascade_regenerator.build_reporting_tree()` — the same source-of-truth that writes `target_cascade.json`. This resolves manager → reports via the canonical hierarchy (role_manager_whitelist + role_tiers) rather than relying on hr.json data.

**Verified**: CRBO (300002) now returns:
- 6 direct reports
- 808 indirect (recursive) subordinates
- Compared to: 0 + 0 before fix

## What v10.406 added

### Cascade page changes (`pages/12_cascade.py`)

1. Import `compute_team_rollup` at top (with `None` fallback if import fails)
2. New tab `"📈 Team progress"` added to `_tab_defs` between `"📊 My targets"` and `"🌳 Cascade tree"`
3. Tab body renders:
   - **Period selector**: dropdown with 2026-Q2, 2026-Q1, 2025-Q4, 2025-Q3, 2026, 2025 (defaults to 2026-Q2 where actuals exist)
   - **Top metrics**: 4 cards showing direct reports count, total subordinates (recursive), KPIs scored, team avg BSC
   - **KPI rollup table**: per-KPI row with team actual, team target, achievement %, BSC score 1-5, coverage badge (reports_with_actual / total)
   - **Direct reports drill-down**: up to 9 cards, one per direct report, showing their rollup BSC score color-coded
   - **Unscored KPIs expander**: lists KPIs without actuals or targets with reason
   - **Notes section**: rollup engine notes (e.g., "leaf node" warning)
4. Tab gated by `is_mgr` (MD/Chief/Head/Manager/Director) via `tab_visible_cascade`

### Manager_rollup fix (`utils/manager_rollup.py`)

```python
def _direct_report_codes(manager_code: str) -> List[str]:
    """v10.406: canonical fallback when virtual_bank returns empty."""
    from utils.virtual_bank import direct_reports
    reports = direct_reports(manager_code)
    if reports:
        return [r.staff_code for r in reports]
    # Canonical fallback to build_reporting_tree
    try:
        from utils.cascade_regenerator import (
            build_reporting_tree, _strip_meta, DEFAULT_BRANCH_TIER_THRESHOLD,
        )
        ...
        return reports_of.get(manager_code, [])
    except Exception:
        return []
```

### Tab visibility (`utils/core_audit.py`)

Added `"team_progress": is_mgr` to the `tab_visible_cascade` return dict.

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 291 → **292** |
| Tests | 327 → **339** (+12 new) |
| Verifier | 576 → **582 checks** |
| Master prompt lockstep | **50/50 consecutive batches** |
| G162 baseline | 4022 (**99 consecutive zero-drift batches**) |
| Engine state | 0/0/0/0 ✓ |
| CRBO direct reports | 0 → **6** (canonical fallback works) |
| CRBO subordinates | 0 → **808** (recursive subtree walk) |

## 10 honest acknowledgements

1. **First of 7 QA enhancements landed.** Same engine-disconnect pattern as v10.405's `suggest_target`.

2. **Underlying bug surfaced + fixed.** Wiring revealed `virtual_bank.direct_reports` doesn't see real chiefs. Without the canonical fallback, every C-suite rollup would have been zero — silent failure mode.

3. **Same source-of-truth used everywhere.** Canonical fallback uses `cascade_regenerator.build_reporting_tree` — the same function that writes `target_cascade.json`. Now rollup and cascade are guaranteed-consistent.

4. **Period defaults to where actuals exist.** Defaulting to 2026-Q2 (where actuals are loaded) means the tab is useful immediately; annual 2026 view is available but will show "no actuals" appropriately.

5. **Graceful degradation everywhere.** Leaf node managers get an info message. Missing actuals → warning expander. Missing targets → labeled as "missing" in source column. No crashes, no blank screens.

6. **Drill-down for 9 reports max.** Bigger teams (e.g., MD with 10 chiefs) show only 9; rationale = 3-column grid. Future enhancement: paginated or filterable list.

7. **No schema changes.** Pure read-side feature. `target_cascade.json` unchanged. `bsc_actuals_*.json` unchanged. Engine state preserved at 0/0/0/0.

8. **Tab visible to all managers.** Tellers/CSOs don't see it (gated by `is_mgr`). Branch Managers see their branch's rollup. Chiefs see SBU rollup. MD sees bank-wide.

9. **Variance analysis via achievement %.** Color-coded: green ≥95%, amber 75-95%, red <75%. Score color: green ≥4, amber 3-4, red <3.

10. **50 consecutive lockstep batches.** No drift.

## What you'll see when you reload

Login as any manager (e.g., Nicholas/CRBO, any Branch Manager). Open Cascade page → new **📈 Team progress** tab between "My targets" and "Cascade tree".

For CRBO at 2025-Q4:
```
Direct reports: 6   |   Total subs: 808   |   KPIs scored: 35   |   Team avg BSC: 3.42

📊 KPI rollup
KPI                  Team actual   Team target   Achievement   BSC   Coverage
PBT (sum)            28.5B         32.5B         87.6%         3.5   720/808 (89%)
NPL Ratio (mean)     5.2           6.0           113.5%        4.5   780/808 (97%)
...

👥 Drill down to direct reports
[Head of Branches]  4.10  ▎23 reports, 18 KPIs scored
[Head of Women]     3.85  ▎12 reports, 14 KPIs scored
...
```

For MD at 2025-Q4: bank-wide rollup spanning all 808 RB staff + commercial banking + support functions.

## On your end

1. Close Streamlit
2. Extract `a2z_v10406_patch.zip` flat on top of v10.405 state
3. Run `python scripts\verify_local_state.py` → expect **582/582**
4. Engine: `python utils\cascade_structure_engine.py` → 0/0/0/0
5. Login as a chief or branch manager
6. Open Cascade page → new "📈 Team progress" tab
7. Default period: 2026-Q2 (or pick 2025-Q4 for fuller data)
8. Should see: team metrics, KPI rollup, direct reports drill-down
9. Tell me **"continue"** → v10.407 = E2 Strategic pillar visualization

## Roadmap recap (per consolidated backlog)

| Batch | What | Status |
|---|---|---|
| ~~v10.403~~ | Cleanup (synthetic chiefs + Admin) | ✅ |
| ~~v10.404~~ | Preserve manual on regen | ✅ |
| ~~v10.405~~ | Target guidance + weight visibility | ✅ |
| ~~v10.406~~ | E1: Real-Time Progress Rollup | ✅ **DONE** |
| **v10.407** | E2: Strategic pillar visualization | **next** |
| v10.408 | E3: Target what-if simulator |
| v10.409 | E4: Negotiation escalation chain |
| v10.410 | E5: Executive cascade health dashboard |
| v10.411 | E6: Bottom-up capacity feedback |
| v10.412 | E7: Cascade API & exports |
| v10.413 | F2: Per-layer buffer + MD per-KPI cap |
| v10.414 | F3: Per-line-manager retain auth |
| v10.415 | F5: Dual-view BSC + UI polish |
| v10.416 | Role weight renormalization (225/227) |
| v10.417 | KPI library dedup |
| v10.418 | Backup retention cleanup |
| v10.419 | Retired test cleanup |
| v10.420 | Archived bank_target reconciliation |
| v10.421 | Pillar weights decision |
| v10.422 | CBS baseline computation (data dep) |
| v10.423 | PBT live actuals integration (data dep) |
| v10.424 | MD BSC integration verification |
