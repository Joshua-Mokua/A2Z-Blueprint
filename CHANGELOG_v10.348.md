# Changelog — v10.348 Competitor Hub Consolidation (Option E sub-batch 4)

**Date:** 2026-05-12
**Phase:** 4 (thirty-third arc — fourth E batch)
**Audit:** 235/235 gates PASS = 100.0%
**Tests:** 10 new in `test_v10348_competitor_hub_consolidation.py`, all passing
**Page smoke:** 122/122 PASS at 100%
**Verifier:** 80/80 checks pass on a clean extract
**G162 Baseline:** 4022 (42 consecutive zero-drift batches)

---

## Your ask

> "Competitor"

Fourth E batch. Same Pattern S as the previous three. Smallest cluster tier (2 pages) — same shape as Propositions (v10.347).

## What v10.348 delivered

### Helper module: `utils/competitor_hub_render.py` (787 lines)

Single source of truth for 2 competitor render functions:

| Function | Source page | What it renders |
|---|---|---|
| `render_competitor_overview(actor)` | `11_competitor.py` | 5 tabs: Market Overview / Rate Comparison / KPI Benchmarking / Market Share / AI Market Brief |
| `render_competitor_workbench(actor)` | `93_competitor_intelligence.py` | 8 tabs wrapping the v10.278 cluster engines: data collection, rates, digital intel, gap analysis, alerts, strategic response, exec radar, API |

Cache helpers domain-prefixed (`_overview_load`, `_workbench_bootstrap_engines`) to avoid Streamlit cache collisions.

### Thin wrapper pages

| Page | Before → After | Audience |
|---|---|---|
| `11_competitor.py` | 168 → **26** lines | Sales / strategy team |
| `93_competitor_intelligence.py` | 615 → **27** lines | Heavy operational (strategy / competitive intel team) |
| **Total** | **783 → 53 lines** (-93%) | |

### Consolidated entry: `pages/118_competitor_hub.py` (126 lines)

```
┌────────────────────────────────────────────────────────────────┐
│  🎯 Competitor Hub                                              │
├────────────────────────────────────────────────────────────────┤
│  Area:  [ 📊 Market Overview ]  [ 🛠️ Workbench ]                 │
├────────────────────────────────────────────────────────────────┤
│   [tab1] [tab2] [tab3] [tab4] [tab5] (or [tab1-8])              │
│                                                                  │
│   ... selected area content ...                                  │
└────────────────────────────────────────────────────────────────┘
```

- **Top-level**: `st.segmented_control` selects one of 2 areas. Default = first area the user has access to.
- **Per-area access gating preserved**. Users only see pills for areas they can access. A user with only `external.competitor_intel` sees just Market Overview.
- **Hard `require_access` enforcement when an area is selected** (defense in depth).

### Two areas, two audiences, both preserved

| Area | Access | Audience |
|---|---|---|
| 📊 Market Overview | `external.competitor_intel` | Sales / strategy — Kenya banking market view (rates, market share, KPI benchmarking, AI Market Brief) |
| 🛠️ Workbench | `shared.customer_360` | Heavy operational — full 8-engine pipeline (data collection, rates, digital intel, gap analysis, alerts, strategic response, exec radar, API) |

### G235 audit gate

Locks the architecture:
1. `utils/competitor_hub_render.py` exists with both render functions
2. Both old pages are ≤40 lines (thin wrappers)
3. Each old page imports its render function
4. Helper module does NOT import from `pages.*` (layer rule)
5. `pages/118_competitor_hub.py` exists and imports both renders
6. All 3 pages smoke-test PASS

### Reversibility (Pattern M)

`data/_v10348_backups/` contains the pre-v10.348 bodies:
- `11_competitor.py.before` (168 lines)
- `93_competitor_intelligence.py.before` (615 lines)

Restoration is `cp data/_v10348_backups/<name>.before pages/<name>`.

## Pattern S now proven across four clusters

| Batch | Cluster | Pages | Reduction |
|---|---|---|---|
| v10.345 | Live Cockpits | 4 → 5 (+115) | 1,946 → 107 = **-94%** |
| v10.346 | Finance Hub | 4 → 5 (+116) | 2,519 → 104 = **-96%** |
| v10.347 | Propositions Hub | 2 → 3 (+117) | 955 → 52 = **-95%** |
| v10.348 | Competitor Hub | 2 → 3 (+118) | 783 → 53 = **-93%** |
| **Total across 4 E batches** | | **12 → 16 pages** | **6,203 → 316 lines = -95%** |

Same shape every time: helper module with namespaced render functions, thin wrappers preserving access gates, consolidated entry with segmented selector, audit gate locking the architecture, backups preserved.

## What v10.348 deliberately did NOT do

- **Did not delete original pages.** Originals remain bookmarkable and functional; deletion is a separate batch after parity is confirmed on localhost.
- **Did not modify `utils/cockpit_read.py` or competitor engines.** Same engine layer, same data feeds.
- **Did not consolidate the 4 hubs (Live, Finance, Propositions, Competitor) into a meta-hub.** Each remains its own entry. Combining them would only be useful if a single user needed all 4 — but the access permissions are different.

## Verified outcome

| Metric | Before → After v10.348 |
|---|---|
| Audit gates | 234 → **235** (G235 added) |
| Page smoke coverage | 121 → **122 pages (100% PASS)** |
| Old pages line count | 783 → **53** (-93%) |
| New helper module | 0 → **787 lines** (single source of truth) |
| New entry point | 0 → **126 lines** |
| New audit gate | G234 → **G235** |
| Verifier checks | 73 → **80** |
| G162 baseline | 4022 (42 consecutive zero-drift batches) |

## Files changed

| File | Change |
|---|---|
| `utils/competitor_hub_render.py` | NEW — 787 lines, single source of truth |
| `pages/11_competitor.py` | 168 → 26 lines (thin wrapper) |
| `pages/93_competitor_intelligence.py` | 615 → 27 lines (thin wrapper) |
| `pages/118_competitor_hub.py` | NEW — 126 lines, consolidated entry |
| `pages/_manifest.json` | Registered `118_competitor_hub.py` |
| `scripts/audit.py` | New gate G235 |
| `scripts/build_competitor_hub_render.py` | NEW — repeatable generator |
| `scripts/verify_local_state.py` | Extended to 80 checks |
| `data/_v10348_backups/*.before` | Pre-v10.348 page bodies preserved (Pattern M) |
| `tests/integration/test_v10348_competitor_hub_consolidation.py` | NEW — 10 tests |

## Suggested direction for v10.349

Two E candidates left, plus original roadmap:

1. **You verify v10.348 on localhost first** ← recommended
2. **v10.349 — Option E sub-batch 5: Platform/IT** (`91_systems_view` + `96_it_digital_pt1` + `97_it_digital_pt2` + `98_platform_health` — 4 pages, Finance-sized)
3. **v10.349 — Convert all consolidated originals to thin redirects** (Live Cockpits + Finance + Propositions + Competitor — 12 pages → redirect stubs, after parity confirmed)
4. **v10.349 — Continue original roadmap** (partnerships P&L, B-027 tail, Strategic Initiative engine)

Which way?
