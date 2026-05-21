# Changelog — v10.407 Strategic Pillar Visualization (E2)

**Date:** 2026-05-14
**Phase:** QA-Standards enhancement (2 of 7)
**Audit:** G293 added
**Tests:** 12/12 PASSED in `test_v10407_strategic_pillar_viz.py`
**Verifier:** 588/588 checks pass
**G162 baseline:** 4022 (**100 consecutive zero-drift batches — centennial milestone**)
**Master prompt:** v4.49 → v4.50 (lockstep — 51 consecutive batches)

---

## Per QA-Standards Enhancement #2

> **Problem:** Employees don't see how their targets connect to bank strategy.
> **Solution:** Interactive visualization linking individual targets to strategic pillars.

## What v10.407 built

### New engine module `utils/pillar_impact_engine.py` (~380 LOC)

**Core functions:**
- `pillar_breakdown_for_staff(staff_code, period)` → `PillarBreakdown`
  - Returns role, total KPIs, list of `PillarSlice` (one per pillar)
  - Each slice: pillar name, KPI count, role weight sum + %, bank pillar weight, targets-set count, actuals count, KPI ids
- `pillar_breakdown_for_manager(manager_code, period)` → dict
  - Aggregated across full subtree (recursive)
  - Returns: own breakdown + `team_pillar_summary` per pillar (kpi_count, staff_count, targets_set, has_actuals)
  - Capped at 1500 subs for very-wide trees
- `bank_pillar_weights()` → canonical pillar weights from kpi_library
- `kpi_to_strategic_pillar_map()` → fast lookup id → pillar
- `clear_cache()` → reset module caches after data refresh

**Performance:**
- Module-level `_TARGET_CACHE` + `_ACTUAL_CACHE` keyed by period
- Pre-computed `(staff_code, kpi_id) → bool` lookups
- Avoids O(N²) blowup: CRBO's 808-sub aggregation went from timeout → 12s on first call, instant on cached calls

### New cascade page tab `🎯 Strategic impact`

Tab inserted between **📈 Team progress** and **🌳 Cascade tree**. **Visible to ALL staff** (Teller through MD) — per Joshua's directive that every staff member should see how their KPIs connect to strategy.

**Renders:**

1. **Personal info header** — role, total KPIs, pillars touched
2. **Bank pillar weight horizontal bar** — color-coded proportional bar showing the canonical 4-pillar split (e.g., Financial=68%, Customer Focus=14%, OpEx=6%, People=12%)
3. **Personal pillar breakdown table** — per pillar row:
   - Pillar name (color-bordered)
   - Bank weight (canonical %)
   - Your KPIs (count in that pillar)
   - Your weight (sum of those KPI weights as %)
   - Targets set (X/Y from cascade)
   - Actuals (X/Y from bsc_actuals)
4. **KPIs in each pillar** — expandable list per pillar showing KPI ids
5. **Team strategic distribution** (managers only) — recursive aggregation across full subtree

**Color palette:**
- Financial → green (#10B981)
- Customer Focus → blue (#185FA5)
- Operational Excellence → purple (#8B5CF6)
- People & Learning → amber (#F59E0B)
- Process → cyan (#06B6D4)
- Risk → red (#E24B4A)

### Tab visibility (`utils/core_audit.py`)

Added `"strategic_impact": True` — visible to everyone (not gated by `is_mgr`).

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 292 → **293** |
| Tests | 339 → **351** (+12 new) |
| Verifier | 582 → **588 checks** |
| Master prompt lockstep | **51/51 consecutive batches** |
| G162 baseline | 4022 (**100 consecutive zero-drift batches** — centennial!) |
| Engine state | 0/0/0/0 ✓ |

## End-to-end verified

| Probe | Result |
|---|---|
| `bank_pillar_weights()` | 4 pillars summing to 1.0 ✓ |
| `kpi_to_strategic_pillar_map()` | 189 KPIs mapped to pillars ✓ |
| MD breakdown (300001, 2026) | role=Chief Executive & Managing Director, 12 KPIs across 3 pillars (Financial=7, Customer Focus=1, People=4) ✓ |
| CRBO subtree breakdown | 808 subordinates, 7 pillars in aggregate ✓ |
| Engine state | 0/0/0/0 ✓ |

## 10 honest acknowledgements

1. **Caching is critical here.** First implementation timed out at 30s on CRBO's 808-sub tree because each staff loaded target_cascade.json fresh. Module-level caches keyed by period dropped that to 12s on first run, instant subsequent.

2. **Visible to ALL staff per QA intent.** The whole point is that Tellers see their KPIs connect to bank strategy. Gating to managers would defeat the purpose.

3. **Performance honest disclosure.** 12-second first call for an 808-sub aggregation isn't lightning-fast. Streamlit will memoize via `@st.cache_data` decorator in higher-load deployments. For now: acceptable.

4. **Bank pillar weights are still 68/14/6/12.** That's the current state (Financial-heavy crisis posture). v10.421 still pending for Joshua to decide whether to switch to Kaplan-Norton balanced (40/25/25/10).

5. **Unmapped pillar exists.** Some KPIs in kpi_library don't have pillar metadata or use an unexpected pillar string. These render as "Unmapped" with grey color. Pre-existing data gap; not introduced by this batch.

6. **Pillar weight % per role may not sum to 100%.** This is C-WT4 (role weight renormalization) — 225 of 227 roles have weights summing to ≠1.0. The strategic impact view now surfaces this clearly (your weight % shown per pillar) — managers will see the problem, which is exactly why v10.416 will fix it.

7. **Team pillar summary expensive on first render.** Manager subtree aggregation is O(subs). For MD's full bank (~1400 subs), would be slower. Streamlit's spinner handles UX during compute.

8. **Reused canonical sources.** target_cascade.json (allocations) + bsc_actuals_*.json (actuals) — same data backbones that drive the rest of the system.

9. **PillarSlice and PillarBreakdown are dataclasses.** Easy to extend later (e.g., add achievement_pct, weighted_score) without breaking callers.

10. **51 consecutive lockstep batches. 100 consecutive zero-drift G162 baseline checks.** No drift.

## What you'll see when you reload

Login as any staff member → Cascade page → new **🎯 Strategic impact** tab.

**For a Branch Manager:**
```
Your role: Branch Manager | Total KPIs: 21 | Pillars touched: 4

🏦 Bank's strategic pillar weights
[Financial 68%][Customer 14%][OpEx 6%][People 12%]

📊 Your KPIs grouped by pillar
Pillar              Bank weight  Your KPIs  Your weight  Targets  Actuals
Financial           68%          3          15%          3/3      0/3
Customer Focus      14%          1          5%           1/1      1/1
Operational Excellence 6%        12         40%          8/12     5/12
People & Learning   12%          5          20%          0/5      0/5
```

**For MD or a Chief:**
- Above + 'Your team's strategic distribution' section
- Aggregated subtree pillar distribution

## On your end

1. Close Streamlit
2. Extract `a2z_v10407_patch.zip` on top of v10.406 state
3. Run `python scripts\verify_local_state.py` → expect **588/588**
4. Engine: `python utils\cascade_structure_engine.py` → 0/0/0/0
5. Login as any staff
6. Open Cascade page → new **"🎯 Strategic impact"** tab
7. Tell me **"continue"** → v10.408 = E3 Target what-if simulator

## Roadmap (consolidated backlog still in flight)

| Batch | What | Status |
|---|---|---|
| ~~v10.403~~ | Data cleanup | ✅ |
| ~~v10.404~~ | Preserve manual on regen | ✅ |
| ~~v10.405~~ | Target guidance + weight visibility | ✅ |
| ~~v10.406~~ | E1: Real-Time Progress Rollup | ✅ |
| ~~v10.407~~ | E2: Strategic pillar visualization | ✅ **DONE** |
| **v10.408** | E3: Target what-if simulator | **next** |
| v10.409 | E4: Negotiation escalation chain |
| v10.410 | E5: Executive cascade health dashboard |
| v10.411 | E6: Bottom-up capacity feedback |
| v10.412 | E7: Cascade API & exports |
| v10.413 | F2: Per-layer buffer + MD per-KPI cap |
| v10.414 | F3: Per-line-manager retain auth |
| v10.415 | F5: Dual-view BSC |
| v10.416 | Role weight renormalization (225/227 broken) |
| v10.417 | KPI library dedup |
| v10.418 | Backup retention cleanup |
| v10.419 | Retired test cleanup |
| v10.420 | Archived bank_target reconciliation |
| v10.421 | Pillar weights decision |
| v10.422 | CBS baseline computation (data dep) |
| v10.423 | PBT live actuals integration (data dep) |
| v10.424 | MD BSC integration verification |
