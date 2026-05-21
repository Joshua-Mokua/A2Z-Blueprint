# Changelog — v10.346 Finance Hub Consolidation (Option E sub-batch 2)

**Date:** 2026-05-12
**Phase:** 4 (thirty-first arc — second E batch)
**Audit:** 233/233 gates PASS = 100.0%
**Tests:** 12 new in `test_v10346_finance_hub_consolidation.py`, all passing
**Page smoke:** 120/120 PASS at 100%
**G162 Baseline:** 4022 (unchanged — helper added to EXEMPT_FILES per Pattern L)

---

## Your ask

> "continue v10.346 — Option E sub-batch 2: Finance hub. I confirm have seen the unified but still the individual cockpits are there"

Second E batch. v10.345 confirmation acknowledged — the Live Cockpits unified page on `/115` plus the originals on `/109-112` is the **intended** behavior. Originals stay functional until you've used the unified view long enough to be sure parity holds, then a later batch can convert them to thin redirects.

This batch applies the same Pattern S to the Finance cluster: `9_sbu` + `10_opex` + `52_mgmt_accounts` + `114_sbu_drilldown` → one consolidated entry.

## What v10.346 delivered

### Helper module: `utils/finance_hub_render.py` (2,554 lines)

Single source of truth for 4 finance render functions:

| Function | Source page | What it renders |
|---|---|---|
| `render_sbu_performance(actor)` | `9_sbu.py` | 5 tabs: Profitability / Branch P&L / Regional / Turnaround / Action plans |
| `render_sbu_drilldown(actor)` | `114_sbu_drilldown.py` | 7 tabs: Bank P&L / Retail / Commercial / CBK Sector / RM-Tagged / Propositions / Balance Sheet |
| `render_opex(actor)` | `10_opex.py` | 6 tabs: Bank Summary / SBU P&L / Branch P&L / Staff / OpEx / Arc Engines |
| `render_mgmt_accounts(actor)` | `52_mgmt_accounts.py` | 7 tabs: P&L / Balance Sheet / Trend / Ratios / OCI / Export / Arc Engines |

Cache helpers domain-prefixed (`_opex_load`, `_mgmt_accounts_load`) to avoid Streamlit cache collisions between domains — both pages had a `_load()` function.

### Thin wrapper pages

| Page | Before → After | Audience |
|---|---|---|
| `9_sbu.py` | 825 → **26** lines | Branch managers, regional heads |
| `10_opex.py` | 431 → **24** lines | CIR analysts, efficiency analysts |
| `52_mgmt_accounts.py` | 836 → **24** lines | CFO, board |
| `114_sbu_drilldown.py` | 427 → **30** lines | Customer-value strategists |
| **Total** | **2,519 → 104 lines** (-96%) | |

### Consolidated entry: `pages/116_finance_hub.py` (149 lines)

```
┌────────────────────────────────────────────────────────────────┐
│  💰 Finance Hub                                                 │
├────────────────────────────────────────────────────────────────┤
│  Area: [📊 Mgmt Accounts] [🏦 SBU Performance] [🏘️ Drilldown] [📐 OpEx]
├────────────────────────────────────────────────────────────────┤
│  (selected area's native 5-7 tab cockpit)                       │
└────────────────────────────────────────────────────────────────┘
```

- **`st.segmented_control` area selector** (radio fallback for older Streamlit)
- **Per-area access gating preserved**: SBU Performance + SBU Drilldown share `finance.sbu_performance`; OpEx uses `operations.opex`; Mgmt Accounts uses `finance.mgmt_accounts`. Users only see pills they can access.
- **Hard `require_access` enforcement** when an area is selected — defense in depth even though pills are pre-filtered.
- **Selection persists** across reruns via `session_state["finance_hub_selected_key"]`.
- **Default area** = Management Accounts (CFO is the largest finance audience).

### Architectural fix layered in: the shim move

Building the helper surfaced a real architectural issue. The original pages imported `load_shared_state` (from `pages/_shared.py`) and `require_access` (from `pages/_access.py`). When those imports moved into `utils/finance_hub_render.py`, G128 fired:

> `LAYER_VIOLATION @ utils.finance_hub_render: utils/ module imports from pages/ — forbidden layer crossing`

Per the project's hard rule (FORBIDDEN_LAYER_EDGES in `utils/structure_audit_core.py`): `utils → pages` is forbidden. Business logic can't depend on UI.

**The fix: shim move.** Four shared infrastructure modules moved to their architecturally correct home:

| Old path (now thin shim) | New canonical home |
|---|---|
| `pages/_shared.py` | `utils/page_shared.py` |
| `pages/_access.py` | `utils/page_access.py` |
| `pages/_cockpit_render.py` | `utils/page_cockpit_render.py` |
| `pages/_manifest_loader.py` | `utils/page_manifest_loader.py` |

Each `pages/_*.py` is now a ~10-line file that does `from utils.page_X import *`. Every existing `from pages._shared import load_shared_state` keeps working unchanged via the shim. The helper imports from `utils.page_*` directly — no layer crossing.

This was overdue. These modules ARE shared infrastructure (access control, shared state loaders, manifest reader, cockpit render helpers); they belong in `utils/`, not `pages/`. The shim preserves backward compatibility for the hundreds of `from pages._*` imports across the codebase.

`utils/page_manifest_loader.py` also got a path correction: it now reads `pages/_manifest.json` (canonical location) regardless of where the module itself lives.

### Build script: `scripts/build_finance_hub_render.py`

Programmatic extractor that:
1. Reads source pages from `data/_v10346_backups/` (the originals, since the live pages are now thin wrappers)
2. Splits on `require_access(...)` line: preamble (imports + helpers) vs body (renders)
3. **Rewrites `pages._*` imports** to `utils.page_*` automatically — both top-level and nested (inside function bodies, which `ast.walk` would still flag)
4. Domain-prefixes colliding helper names (`_load` → `_opex_load`, `_mgmt_accounts_load`)
5. Composes the helper module with sorted imports + render functions

Idempotent — re-running produces identical output. Preserved for future regeneration if the originals are ever updated.

## Audit gate patches

Five gates that examined specific strings in the old page bodies (engine imports, `st.tabs` calls, etc.) needed updating because those strings moved to the helper:

- **G136** (finance_arc_ui_integrated) — now reads `utils/finance_hub_render.py` source alongside finance pages
- **G157** (resource_optimization_arc_ui_integrated) — same pattern, for operations pages
- **G227** (sbu_drilldown_integration) — checks for `st.tabs` in 114's source OR the helper

Mechanical patches following the same pattern established in v10.345.

## New audit gate: G233

Locks the consolidation invariants:
1. `utils/finance_hub_render.py` exists with all 4 render functions
2. Each of the 4 old pages is ≤40 lines (thin wrapper)
3. Each old page imports its corresponding render function
4. `pages/116_finance_hub.py` exists and imports all 4 render functions
5. **Shim move verification**: canonical homes exist in `utils/`; shims at `pages/_*.py` re-export from `utils/`
6. All 5 finance pages smoke-test PASS

## Engine hub registration: Tier 62

Added "Tier 62 — Finance Hub Consolidation (v10.346)" to `ENGINE_HUB_TIERS` in `pages/7_admin.py`, registering 5 new engines:

| Engine | Why registered |
|---|---|
| `finance_hub_render` | The consolidation helper |
| `page_shared` | Canonical home for `load_shared_state` |
| `page_access` | Canonical home for `require_access` |
| `page_cockpit_render` | Canonical home for shared cockpit helpers |
| `page_manifest_loader` | Canonical home for manifest loader |

## Pattern L applied

`utils/finance_hub_render.py` added to G162 EXEMPT_FILES — same rationale as `utils/segment_classifier.py`, etc. The helper contains the bodies of 4 finance pages that include tenant-defining content (KES amounts, CBK regulatory thresholds, Tier-2 Kenya bank labels embedded in P&L pack templates). Per Pattern L: files that DEFINE tenant identity are exempt; only files that CONSUME identity must use `cfg()` helpers.

## Reversibility (Pattern M)

`data/_v10346_backups/` contains:
- `9_sbu.py.before` (825 lines)
- `10_opex.py.before` (431 lines)
- `52_mgmt_accounts.py.before` (836 lines)
- `114_sbu_drilldown.py.before` (427 lines)
- `_shared.py.before` (89 lines)
- `_access.py.before` (139 lines)
- `_cockpit_render.py.before` (162 lines)
- `_manifest_loader.py.before` (192 lines)

If anything regresses, originals can be restored.

## What v10.346 deliberately did NOT do

- **Did not delete any of the 4 original finance pages.** They become deletion candidates after you confirm parity on localhost.
- **Did not modify business logic.** Same data sources, same calculations, same access gates.
- **Did not unify access permissions.** SBU + Drilldown still share `finance.sbu_performance`; OpEx still uses `operations.opex`; Mgmt Accounts still uses `finance.mgmt_accounts`. Three distinct permissions because three distinct audiences.
- **Did not address the SBU semantic overlap.** Both `9_sbu` (branch-as-SBU) and `114_sbu_drilldown` (segment-as-SBU) are preserved as separate views. They're two valid decompositions of the same total. If you want to unify them, that's a separate design conversation.

## Verified outcome

| Metric | Before → After v10.346 |
|---|---|
| Audit gates | 232 → **233** (G233 added) |
| Page smoke coverage | 119 → **120 pages (100% PASS)** |
| Old pages line count | 2,519 → **104** (-96%) |
| New helper module | 0 → **2,554 lines** |
| New entry point | 0 → **149 lines** |
| New canonical homes in utils/ | 0 → **4** (page_shared / page_access / page_cockpit_render / page_manifest_loader) |
| Engine hub coverage (G117) | 94.2% → **95.0%+** (Tier 62 added) |
| G128 layer integrity | preserved after shim move |
| G162 baseline | 4022 (unchanged — helper exempt per Pattern L) |
| Verifier checks | 51 → **66** |

## Files changed

| File | Change |
|---|---|
| `utils/finance_hub_render.py` | NEW — 2,554 lines, single source of truth |
| `pages/9_sbu.py` | 825 → 26 lines (thin wrapper) |
| `pages/10_opex.py` | 431 → 24 lines (thin wrapper) |
| `pages/52_mgmt_accounts.py` | 836 → 24 lines (thin wrapper) |
| `pages/114_sbu_drilldown.py` | 427 → 30 lines (thin wrapper) |
| `pages/116_finance_hub.py` | NEW — 149 lines (consolidated entry) |
| `pages/_shared.py` | 89 → 12 lines (shim) |
| `pages/_access.py` | 139 → 22 lines (shim) |
| `pages/_cockpit_render.py` | 162 → 9 lines (shim) |
| `pages/_manifest_loader.py` | 192 → 8 lines (shim) |
| `utils/page_shared.py` | NEW — canonical home (89 lines) |
| `utils/page_access.py` | NEW — canonical home (139 lines) |
| `utils/page_cockpit_render.py` | NEW — canonical home (162 lines) |
| `utils/page_manifest_loader.py` | NEW — canonical home (193 lines, path-corrected) |
| `pages/7_admin.py` | New "Tier 62 — Finance Hub Consolidation" in ENGINE_HUB_TIERS |
| `pages/_manifest.json` | Registered `116_finance_hub.py` |
| `scripts/audit.py` | G233 + G136/G157/G227 patches + EXEMPT_FILES update + FOUNDATIONAL update |
| `scripts/build_finance_hub_render.py` | NEW — one-shot generator |
| `scripts/verify_local_state.py` | Extended to 66 checks |
| `data/_v10346_backups/*.before` | 8 originals preserved (4 pages + 4 shim sources) |
| `tests/integration/test_v10346_finance_hub_consolidation.py` | NEW — 12 tests |

## Backlog status

| ID | Status |
|---|---|
| B-009 – B-018 | Open |
| B-027 (tail) | Mostly closed |
| B-028, B-029 | Open |
| B-030, B-034, B-039, B-040 | Closed |
| B-041 | Open (validate_before_save in more producers) |
| B-042, B-043 | Documented (Option E divergences) |
| B-044 (Live Cockpits → redirects) | Pending your confirmation |
| B-045 (Option E sub-batch 2 candidates) | **Partially closed — Finance Hub done, Propositions/Competitor/Platform remain** |
| B-046 NEW (Finance pages → redirects) | Pending your confirmation |
| B-047 NEW (SBU semantic overlap — unify branch-as-SBU and segment-as-SBU) | Design conversation needed |

## Suggested next direction

Five candidates for v10.347:

1. **Verify v10.346 on localhost first** ← recommended (this is the bigger of the E batches; harder to fix in retrospect)
2. **v10.347 — Option E sub-batch 3: Propositions** — `27_propositions` + `92_propositions_workbench` → one Propositions module
3. **v10.347 — Option E sub-batch 3: Competitor** — `11_competitor` + `93_competitor_intelligence` → one Competitor module
4. **v10.347 — Convert v10.345 + v10.346 originals to thin redirects** — after parity confirmed
5. **v10.347 — Continue original roadmap** — B-027 tail / partnerships P&L / Strategic Initiative engine

My honest recommendation: **verify v10.346 on localhost first.** This batch shipped a real architectural change (the shim move). The audit + smoke run is green, but it's prudent to confirm shims work for live pages too before stacking more consolidation.

Which way?
