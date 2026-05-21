# Changelog — v10.408 Target Scenario Simulator (E3)

**Date:** 2026-05-14
**Phase:** QA-Standards enhancement (3 of 7)
**Audit:** G294 added
**Tests:** 12/12 PASSED in `test_v10408_target_scenario_simulator.py`
**Verifier:** 593/593 checks pass
**G162 baseline:** 4022 (101 consecutive zero-drift batches)
**Master prompt:** v4.50 → v4.51 (lockstep — 52 consecutive batches)

---

## Per QA-Standards Enhancement #3

> **Problem:** Managers cannot test "what-if" allocation scenarios.
> **Solution:** Interactive simulator for target allocation scenarios.

## Why this is a NEW module

Earlier deep audit (`E1_E7_ENHANCEMENTS_AUDIT.md`) found `utils/scenario_simulator.py` exists but is **wrong scope** — it handles risk/compliance scenarios (LCR compliance breaches, fraud cascade simulation, disaster recovery) with `ScenarioCategory` enum values like `CUSTOMER_LIFECYCLE`, `CREDIT_LENDING`, `FRAUD_SECURITY`, `RECOVERY_DISASTER`. Not allocation what-ifs.

v10.408 builds the missing piece: a target-cascade what-if simulator.

## What v10.408 built

### New engine `utils/target_scenario_simulator.py` (~420 LOC)

**Core functions:**
- `load_current_scenario(manager_code, kpi, period)` → `ScenarioResult`
- `simulate_alternative(manager_code, kpi, period, alt_allocations)` → `ComparisonReport`
- `compute_scenario(name, ...)` → pure scenario building
- `split_equal(total, to_codes)` → equal-split preset
- `split_weighted_by_history(total, to_codes, kpi)` → proportional-to-history preset
- `_classify_likelihood(new_amount, historical_actual, historical_target)` → 6-band classifier

**6-band likelihood classification:**
| Ratio (new / historical capacity) | Label | Score |
|---|---|---|
| ≤ 0.85 | very likely | 0.95 |
| ≤ 1.00 | likely | 0.85 |
| ≤ 1.10 | on stretch | 0.65 |
| ≤ 1.25 | stretching | 0.45 |
| ≤ 1.50 | very stretching | 0.25 |
| > 1.50 | unrealistic | 0.10 |
| No history | unknown | 0.50 |

**Dataclasses:**
- `AllocationRow` — to_code, to_name, to_role, to_unit, amount, pct_of_total, historical_achievement_pct, likelihood_label, likelihood_score
- `ScenarioResult` — name, kpi, period, total_target, allocated_sum, coverage_pct, rows, notes
- `ComparisonReport` — kpi, period, manager_code, current, alternative, variance_per_row

**Properties:**
- PURE COMPUTATION — does NOT write to `target_cascade.json`
- Manager separately commits via 'Set team targets' tab if they choose to adopt the alternative

### New cascade page tab `🧪 What-if simulator`

Inserted between **🎯 Strategic impact** and **🌳 Cascade tree**. Gated by `is_mgr`.

**UI flow:**
1. KPI + period selector
2. **Current allocation display**: total target, allocated sum, coverage %
3. **Preset split buttons** (4):
   - ⚖️ Equal split — same amount to each recipient
   - 📊 Weight by history — bigger share to historically-stronger performers
   - 🔄 Reset to current — restore current as starting point
   - 0️⃣ Zero out — start from scratch
4. **Per-row alternative inputs** — number_input per recipient with historical hint
5. **🔬 Compare scenarios button** — triggers simulation
6. **Side-by-side comparison table**:
   - Recipient
   - Current amount
   - Alternative amount
   - Δ (delta, color-coded green/red)
   - Likelihood (label, color-coded)
7. **Coverage warnings** — under/over allocated notes
8. **💡 Simulation-only reminder** — manager must commit via Set team targets

### Tab visibility (`utils/core_audit.py`)

Added `"what_if_simulator": is_mgr` — manager-level tool.

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 293 → **294** |
| Tests | 351 → **363** (+12 new) |
| Verifier | 588 → **593 checks** |
| Master prompt lockstep | **52/52 consecutive batches** |
| G162 baseline | 4022 (**101 consecutive zero-drift batches**) |
| Engine state | 0/0/0/0 ✓ |

## End-to-end verified

| Probe | Result |
|---|---|
| `load_current_scenario(300002, PBT, 2026)` | total=65B, 6 reports, 100% coverage ✓ |
| `simulate_alternative` with 50/30/20 split | 3 rows, 100% coverage ✓ |
| `_classify_likelihood(50, 100, 100)` | "very likely", score=0.95 ✓ |
| `_classify_likelihood(200, 100, 100)` | "unrealistic", score=0.10 ✓ |
| `split_equal(1000, 4 codes)` | 250 each ✓ |
| Under-allocation warning | triggers correctly ✓ |
| Engine state | 0/0/0/0 ✓ |

## 10 honest acknowledgements

1. **Wrong-scope `scenario_simulator.py` left untouched.** That module handles risk scenarios (LCR/fraud/disaster) and is used by admin page; not deleting or refactoring it.

2. **Pure computation by design.** Simulator never writes to data. Manager must explicitly commit via Set team targets tab. This is intentional — what-if = sandbox.

3. **Likelihood model is heuristic.** Based on ratio of new target / historical capacity. Not ML. Surfaces "unrealistic" when target is 1.5x what staff has historically achieved.

4. **"Unknown" is the honest default.** When staff has no historical actuals for a KPI (most chiefs for PBT, new hires for anything), simulator returns "unknown (no history)" with score 0.5 — neither encouraging nor discouraging.

5. **No coverage enforcement.** Manager can simulate under-allocation (e.g., 80% coverage) or over-allocation (120%). Warning shown but not blocked. Simulation, not validation.

6. **Preset splits as quick-start.** Equal/Weight-by-history are common starting points; manager then tweaks per-row.

7. **Session state per (manager, kpi, period).** Multiple managers running simultaneously don't collide. Each KPI's draft persists across rerenders.

8. **Comparison table sorted by current order.** Recipients appear in the same order as current cascade for easy mental-mapping.

9. **Performance: instant on small teams, scalable.** CRBO's 6-report PBT loaded in milliseconds. For 100+ direct reports, may slow; not a typical case.

10. **52 consecutive lockstep batches. 101 consecutive zero-drift G162 baseline.**

## What you'll see when you reload

Login as a manager → Cascade page → new **🧪 What-if simulator** tab.

```
KPI: [PBT v]    Period: [2026 v]

📌 Current allocation
Total target: 65B   Allocated sum: 65B   Coverage: 100.0%

🎚️ Build an alternative
[⚖️ Equal split] [📊 Weight by history] [🔄 Reset to current] [0️⃣ Zero out]

Tina Wekesa         Current: 10.8B    Alt: [_____]    hist —
Lorna Matheka       Current: 10.8B    Alt: [_____]    hist —
...

[🔬 Compare scenarios]

⚖️ Comparison: Current vs Alternative
Recipient                Current    Alternative    Δ          Likelihood
Tina Wekesa              10.8B      32.5B         +21.7B     unknown (no history)
Lorna Matheka            10.8B      19.5B         +8.7B      unknown (no history)
...

💡 This is a simulation only. To commit, go to 'Set team targets' tab...
```

## On your end

1. Close Streamlit
2. Extract `a2z_v10408_patch.zip` on top of v10.407 state
3. Run `python scripts\verify_local_state.py` → expect **593/593**
4. Engine: `python utils\cascade_structure_engine.py` → 0/0/0/0
5. Login as a manager
6. Open Cascade page → new **"🧪 What-if simulator"** tab
7. Pick a KPI → see current allocation → try Equal split → adjust → Compare
8. Tell me **"continue"** → v10.409 = E4 Negotiation escalation chain

## Roadmap

| Batch | Status |
|---|---|
| ~~v10.403~~ Data cleanup | ✅ |
| ~~v10.404~~ Preserve manual on regen | ✅ |
| ~~v10.405~~ Target guidance + weight visibility | ✅ |
| ~~v10.406~~ E1: Real-Time Progress Rollup | ✅ |
| ~~v10.407~~ E2: Strategic pillar visualization | ✅ |
| ~~v10.408~~ E3: Target what-if simulator | ✅ **DONE** |
| **v10.409** E4: Negotiation escalation chain | **next** |
| v10.410 E5: Executive cascade health dashboard |
| v10.411 E6: Bottom-up capacity feedback |
| v10.412 E7: Cascade API & exports |
| v10.413 F2: Per-layer buffer + MD per-KPI cap |
| v10.414 F3: Per-line-manager retain auth |
| v10.415 F5: Dual-view BSC |
| v10.416 Role weight renormalization |
| v10.417 KPI library dedup |
| v10.418-v10.421 Housekeeping |
| v10.422-v10.424 CBS / BSC integration verification |
