# CHANGELOG v10.207 — Sixth cockpit absorption (Resource Optimization Arc → 10_opex.py)

**Date:** 2026-05-07
**Theme:** Sixth cockpit absorption batch. Folds
`29_resource_optimization_cockpit.py` (328 lines) into `10_opex.py`
(177 lines) as a 6th top-level "🤖 Arc Engines" tab containing 7
nested sub-tabs. Refactors G157 from location-based to manifest-aware
behavior-based — seventh instance of this pattern. New variant
documented: cockpit with **render functions per tab** instead of
inline tab body. Audit holds at **160/160 PASS**.

## What v10.207 ships

### 1. `pages/10_opex.py` — absorbed Arc Engines as 6th top-level tab

OpEx page goes from 5 → 6 top-level tabs (within G4's 7-tab cap, 1
slot of headroom remaining):

```
🏛️ Bank Summary  📊 SBU P&L  🏢 Branch P&L  👥 Staff Productivity  📐 OpEx Breakdown  🤖 Arc Engines  ← NEW
```

Inside the new tab, 7 nested sub-tabs reproduce the cockpit's structure:

```
📊 Executive       — ExecutiveResourceDashboard (capstone, ENH-165)
🏠 Work Mode        — WorkModeDeclarationEngine
📈 Forecast+TSL     — WorkloadForecastingEngine + TSLOptimizationEngine
⚖️ Balancing+Util   — CrossChannelBalancingEngine + UtilizationDashboardEngine
💚 Wellbeing        — WellbeingIntegrationEngine
🧪 What-If+Invest   — HybridSchedulingSimulator + ResourceInvestmentCaseEngine
🌱 Culture          — IntegrityCultureEngine
```

All 10 engines (ENH-156..165) preserved. Engine instances cached at
session level via `@st.cache_resource` with full constructor wiring
preserved (capstone Executive engine takes the other 9 as deps).

### 2. New absorption variant: render-functions-per-tab

Unlike v10.202..v10.206 cockpits which inlined tab body inside `with
tabs[N]:` blocks, this cockpit defined a **separate render function
per tab** (`render_executive_tab(engines)`,
`render_work_mode_tab(engines)`, etc.) at module level, then called
them from `with tabs[N]:` blocks.

The absorption preserves this design — the 7 functions are copied
into the absorbed section (defined inside the `with sections[5]:`
block scope), then called from `with arc_tabs[N]:`. This is cleaner
than inlining body code; future cockpits using this design can be
absorbed with the same script variant.

### 3. `scripts/audit.py` — G157 refactored to manifest-aware

Seventh instance of the manifest-aware refactor pattern (after G149
v10.199, G151 v10.202, G159 v10.203, G148 v10.204, G153 v10.205,
G155 v10.206). Searches all non-deprecated pages in the `operations`
department, verifies the 10 engine class references appear somewhere.

Note: the cockpit was named `29_resource_optimization_cockpit.py`
(filename) but its target is `10_opex.py` (Operating Leverage page in
the operations department, per manifest). The closure gate searches
the operations department — wherever the engines end up integrated
within Operations, the gate passes.

### 4. `pages/_manifest.json` — cockpit entry removed

Manifest entry for `29_resource_optimization_cockpit.py` deleted.
Manifest goes 103 → 102 pages, 8 → 7 deprecated cockpits.

### 5. `pages/29_resource_optimization_cockpit.py` — DELETED

**⚠️ Manual deletion required when applying this zip:**

```bash
rm pages/29_resource_optimization_cockpit.py
python scripts/audit.py
```

## Files changed (3 modified + 1 deletion)

```
pages/10_opex.py                                MOD  +254 lines  (177 → 431)
                                                      (6th top-level tab + 7 render funcs + 7 nested sub-tabs)
scripts/audit.py                                MOD  +56 lines net  (G157 manifest refactor)
pages/_manifest.json                            MOD  -16 lines  (cockpit entry removed)
pages/29_resource_optimization_cockpit.py       DEL  -328 lines  (manual deletion required)
```

Net cockpit absorption: -328 (cockpit) + +254 (target) - 16 (manifest)
= -90 lines net code reduction.

## Audit

```
Before (v10.206): Score: 160/160 gates = 100.0% — PASS
After  (v10.207): Score: 160/160 gates = 100.0% — PASS
```

## Cockpit absorption schedule — 6/13 done (46%)

| # | Status | Cockpit | Target |
|---|---|---|---|
| 1 | ✅ v10.202 | 26_treasury_arc_cockpit.py | 25_treasury.py |
| 2 | ✅ v10.203 | 15_strategy_arc_cockpit.py | 83_strategy.py |
| 3 | ✅ v10.204 | 16_product_arc_cockpit.py | 5_products.py |
| 4 | ✅ v10.205 | 27_compliance_arc_cockpit.py | 24_compliance.py |
| 5 | ✅ v10.206 | 28_legal_arc_cockpit.py | 26_legal.py |
| 6 | **✅ v10.207** | **29_resource_optimization_cockpit.py** | **10_opex.py** |
| 7 | pending | 93_risk_arc_cockpit.py | 35_stress_testing.py |
| 8 | pending | 94_credit_governance_cockpit.py | 22_credit_analysis.py |
| 9 | pending | 95_revenue_assurance_cockpit.py | 29_revenue_assurance.py |
| 10 | pending | 96_finance_arc_cockpit.py | 52_mgmt_accounts.py |
| 11 | pending | 97_trade_finance_arc_cockpit.py | 46_trade_finance.py |
| 12 | pending | 98_ml_governance_arc_cockpit.py | 91_systems_view.py |
| 13 | pending | 99_integration_cockpit.py | 91_systems_view.py |

Past the halfway point: 6/13 = 46%. At ~1 cockpit per batch,
completion at v10.214.

## Strategic narrative — pattern variant catalog complete

Five tab convention families now documented across the campaign:

| Variant | Cockpit example | Tab convention | Indentation |
|---|---|---|---|
| Hand-paste | v10.202 Treasury | n/a | n/a |
| Named descriptive | v10.203 Strategy | `with tab_form:` etc., body col 4 | col 4 → col 12 |
| Indexed inline | v10.204 Product, v10.205 Compliance | `with tabs[N]:`, body col 8 | col 8 → col 12 |
| Numbered named | v10.206 Legal | `with tabN:` (N=1..7) inside `def render():`, body col 8 | col 8 → col 12 |
| **Render-funcs-per-tab** | **v10.207 Resource Opt** | `with tabs[N]: render_X_tab(engines)`, funcs col 0 | funcs col 0 → col 8 |

All 5 variants now mapped. The absorption script library is
effectively complete — future absorptions should match one of these
5 patterns. After this batch, `scripts/absorb_cockpit.py` can be
extracted with confidence that it covers all observed variants.

## Honest acknowledgements

1. **Render functions preserved as functions, not inlined.** The
   cockpit's design (functions per tab) is cleaner than inlining
   tab body. The absorbed section preserves this — the 7 functions
   are defined inside the `with tabs[5]:` block scope, called from
   `with arc_tabs[N]:`. Total absorbed code: ~120 lines of function
   bodies + ~30 lines of call sites + ~80 lines of engine factory =
   ~230 net new lines vs ~328 cockpit total (reduction = ~98 lines).

2. **`_render_summary` calls renamed to `_ro_render_summary`.** The
   cockpit defined a thin local `_render_summary` wrapper that
   imported `pages._cockpit_render.render_summary`. The absorbed
   section defines `_ro_render_summary` (renamed to avoid name
   collisions if 10_opex defines its own `_render_summary` later) and
   the function bodies have been rewritten to call `_ro_render_summary`
   instead. Functionally identical.

3. **`10_opex.py` is at 6/7 top-level tabs.** 1 slot of headroom
   remaining. Same cap as 24_compliance.py (also 6/7 after v10.205).
   Adding a 7th tab is fine; beyond that requires merging.

4. **Engine constructor dependencies preserved exactly.** The
   cached factory `_get_arc_ro_engines()` instantiates in dependency
   order: leaves (work_mode, forecast, tsl, util), then balance
   (depends on tsl), then wellbeing (depends on util), then hybrid
   (depends on tsl + util + balance), then leaves (invest, culture),
   finally executive (depends on all 9). Same as the cockpit's
   `_build_engines()` function.

5. **The audit_log action renamed** from
   `open_resource_optimization_cockpit` (slightly different from
   the others — was `open_X` here vs `X.view` elsewhere) to
   `resource_optimization_arc_engines.view`. Standardizing the
   naming convention.

6. **Net code reduction: -90 lines.** Reduction trend across all 6
   batches: -132, -99, -86, -109, -97, -90. Mean ≈ -102 lines per
   absorption. Cumulative: -613 lines. Across 13 absorptions,
   projected total ≈ -1300 lines.

7. **G157 refactor is the seventh instance of the same pattern.**
   At seven instances, the helper extraction case is now
   overwhelming. With all 5 tab convention variants observed,
   `scripts/absorb_cockpit.py` extraction can confidently cover
   the entire pattern space. Strong candidate for v10.208.

8. **Page-number collision dropping continues.** Slot 29 was
   claimed by `29_resource_optimization_cockpit.py` and
   `29_revenue_assurance.py`; after v10.207 only revenue assurance
   remains. Net: 7 collisions at v10.197 → 2 collisions after
   v10.207.

9. **17 consecutive clean batches in this session** — v10.193
   through v10.207 (15 code batches + 2 advisory reviews). Cockpit
   absorption sub-campaign past halfway: 6/13 = 46% complete after
   6 batches.

10. **Operations department's manifest count** now 13 → 12. The
    department had `10_opex.py` (target) and
    `29_resource_optimization_cockpit.py` (cockpit, deprecated).
    After absorption + deletion, 12 active operations pages remain
    + 1 deprecated cockpit (`95_revenue_assurance_cockpit.py`,
    pending future absorption).

11. **Looking ahead.** v10.208 candidate: helper extraction
    (`scripts/absorb_cockpit.py`) given the now-complete variant
    catalog. Or continue with v10.208 Risk Arc absorption
    (`93_risk_arc_cockpit.py` → `35_stress_testing.py`) for
    momentum. Both are reasonable.

12. **Looking further ahead — same-target absorptions.**
    `98_ml_governance_arc_cockpit.py` and `99_integration_cockpit.py`
    both target `91_systems_view.py`. The first absorption is
    mechanical; the second needs to integrate into a target whose
    tab structure already includes the first cockpit's content.
    This is the only sequencing dependency in the remaining 7
    absorptions. Should be addressed when we get to v10.213
    (assuming alphabetic order).

## Next batch options

1. **v10.208 — Risk Arc absorption** (`93_risk_arc_cockpit.py`
   → `35_stress_testing.py`). Continue mechanical absorption.
2. **v10.208 — Extract `scripts/absorb_cockpit.py`.** All 5 variants
   now mapped. ~80 lines, single-purpose tooling batch. Future
   absorptions become 1-line invocations. Strong candidate.
3. **v10.208 — Page migration to dotted form.**
4. **v10.208 — Return to deferred platform items.**

I'll continue with **option 1** (Risk absorption) since the pattern
is now mechanical and momentum is strong. The helper extraction
(option 2) becomes natural after another absorption or two — the
remaining batches are all mechanical so the helper saves time
proportionally.
