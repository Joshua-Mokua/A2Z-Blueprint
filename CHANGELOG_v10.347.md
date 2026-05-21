# Changelog — v10.347 Propositions Hub Consolidation (Option E sub-batch 3)

**Date:** 2026-05-12
**Phase:** 4 (thirty-second arc — third E batch)
**Audit:** 234/234 gates PASS = 100.0%
**Tests:** 10 new in `test_v10347_propositions_hub_consolidation.py`, all passing
**Page smoke:** 121/121 PASS at 100%
**Verifier:** 73/73 checks pass on a clean extract
**G162 Baseline:** 4022 (41 consecutive zero-drift batches)

---

## Your ask

> "v10.347 — Option E sub-batch 3: Propositions"

Third E batch. Smallest cluster yet — only 2 pages. Same Pattern S that proved out in v10.345 (Live Cockpits, 4 pages) and v10.346 (Finance Hub, 4 pages).

## What v10.347 delivered

### Helper module: `utils/propositions_hub_render.py` (962 lines)

Single source of truth for the 2 propositions render functions:

| Function | Source page | What it renders |
|---|---|---|
| `render_propositions_performance(actor)` | `27_propositions.py` | 5 tabs: KPI Scorecard / Trend / Branch Contribution / RM Champions / About |
| `render_propositions_workbench(actor)` | `92_propositions_workbench.py` | 8 tabs: Catalog & Approval / Eligibility Check / NBA Preview / Pricing & Fairness / Performance KPIs / A/B Experiments / Dynamic Cohorts / Channel Presentation |

Helper functions domain-prefixed (`_propositions_performance_load_props`, etc.) to avoid Streamlit cache key collisions.

### Thin wrapper pages

| Page | Before → After | Audience |
|---|---|---|
| `27_propositions.py` | 290 → **26** lines | Sales / customer team (performance tracking) |
| `92_propositions_workbench.py` | 665 → **26** lines | Propositions team (operational console) |
| **Total** | **955 → 52 lines** (-95%) | |

### Consolidated entry: `pages/117_propositions_hub.py` (149 lines)

```
┌────────────────────────────────────────────────────────────────┐
│  🎯 Propositions Hub                                            │
├────────────────────────────────────────────────────────────────┤
│  Area:  [ 📊 Performance ]  [ 🛠️ Workbench ]                    │ ← segmented_control
├────────────────────────────────────────────────────────────────┤
│  [tab1] [tab2] ... (5 or 8 sub-tabs depending on area)         │
│                                                                  │
│  ... selected sub-tab content ...                                │
└────────────────────────────────────────────────────────────────┘
```

- **Top-level:** `st.segmented_control` selects Performance vs Workbench
- **Per-area access gating preserved.** Performance gated by `sales_customer.propositions`; Workbench by `shared.customer_360`. **Different audiences** — the hub respects this. A user with only one permission sees only that area's pill.
- **Hard `require_access` enforcement** when an area is selected (defense in depth)
- **Selection persists across reruns** via `session_state["propositions_hub_selected_key"]`

### G234 audit gate

Locks the consolidation:
1. `utils/propositions_hub_render.py` exists with both render functions
2. Helper has NO `from pages.*` imports (layer rule, post-v10.346 shim move)
3. Both old pages are ≤40 lines (thin wrappers)
4. Each old page imports its corresponding render function
5. `pages/117_propositions_hub.py` exists + imports both render functions
6. All 3 pages smoke-test PASS

### Reversibility (Pattern M)

`data/_v10347_backups/` contains the pre-v10.347 bodies:
- `27_propositions.py.before` (290 lines)
- `92_propositions_workbench.py.before` (665 lines)

Restore originals via `cp data/_v10347_backups/<name>.before pages/<name>` if needed.

## Built on v10.346's architectural fix

The build script (`scripts/build_propositions_hub_render.py`) uses the same `_PAGES_SHIM_MAP` mechanism from v10.346 — `pages._shared` → `utils.page_shared`, `pages._access` → `utils.page_access`, `pages._cockpit_render` → `utils.page_cockpit_render`. The helper module is layer-clean from the first build; no post-fixes needed this time.

Compared to v10.345/v10.346, this batch had **zero gate violations** during the build — just the one expected G160 manifest miss, fixed by registering 117 in the manifest. The pattern is now mechanical.

## What v10.347 did NOT do

- **Did not delete the 2 original pages.** Both remain functional alongside; deletion candidates for a future cleanup batch after you confirm parity on localhost.
- **Did not unify the two areas' tabs.** The original "Performance KPIs" (Workbench tab 5) and "KPI Scorecard" (Performance tab 1) appear to overlap — they're preserved as-is. Deduplication is a future Pattern S iteration, would change behavior, not in scope.
- **Did not modify the 8 propositions engines** the Workbench composes. Same engine calls, same data.

## Pattern S — third successful application

Three batches now follow the same mechanical recipe:
1. Feature inventory before code
2. Programmatic extraction into `utils/<cluster>_hub_render.py`
3. Thin wrapper pages (≤40 lines each)
4. Consolidated entry `pages/<NNN>_<cluster>_hub.py`
5. Backups under `data/_v<NNN>_backups/` (Pattern M reversibility)
6. Manifest registration
7. Audit gate G<NNN+200ish> locks the architecture
8. Tier <NN> in `ENGINE_HUB_TIERS` registers the helper engine
9. Tests + verifier extension
10. Flat zip distribution (Pattern R)

The pattern is now well-proven. Future E batches should hit ~30 minutes of build work each.

## Verified outcome

| Metric | Before → After v10.347 |
|---|---|
| Audit gates | 233 → **234** (G234 added) |
| Page smoke coverage | 120 → **121 pages (100% PASS)** |
| Old pages line count | 955 → **52** (-95%) |
| New helper module | 0 → **962 lines** (single source of truth) |
| New entry point | 0 → **149 lines** (consolidated) |
| Backups | 2 originals preserved |
| Verifier | 66 → **73 checks** |
| G162 baseline | 4022 (41 consecutive zero-drift batches) |

## Files changed

| File | Change |
|---|---|
| `utils/propositions_hub_render.py` | NEW — 962 lines, single source of truth |
| `pages/27_propositions.py` | 290 → 26 lines (thin wrapper) |
| `pages/92_propositions_workbench.py` | 665 → 26 lines (thin wrapper) |
| `pages/117_propositions_hub.py` | NEW — 149 lines, consolidated entry |
| `pages/7_admin.py` | New "Tier 63 — Propositions Hub Consolidation (v10.347)" |
| `pages/_manifest.json` | Registered `117_propositions_hub.py` |
| `scripts/audit.py` | New gate G234 + registered in GATES list |
| `scripts/build_propositions_hub_render.py` | NEW — one-shot generator |
| `scripts/verify_local_state.py` | Extended to 73 checks across v10.336-v10.347 |
| `data/_v10347_backups/*.before` | Pre-v10.347 page bodies preserved (Pattern M) |
| `tests/integration/test_v10347_propositions_hub_consolidation.py` | NEW — 10 tests |

## Backlog status

| ID | Status |
|---|---|
| B-044 (Live Cockpit originals → thin redirects) | Pending localhost confirmation |
| B-045 (Option E sub-batch 2: Finance Hub) | **Closed v10.346** ✅ |
| B-046 NEW (Propositions originals → thin redirects) | Pending localhost confirmation |
| B-047 NEW (KPI Scorecard / Performance KPIs overlap dedup) | Documented, deferred |
| B-048 NEW (E sub-batch 4 candidates) | Open |

## What's still open: E sub-batch 4 candidates

Two remaining clusters from the original E plan:

1. **Competitor module** — `11_competitor` + `93_competitor_intelligence` (similar 2-page shape to Propositions)
2. **Platform/IT consolidation** — `91_systems_view` + `96_it_digital_pt1` + `97_it_digital_pt2` + `98_platform_health` (similar 4-page shape to Finance/Cockpits)

Plus the deletion-batch work:
3. Convert Live Cockpit + Finance Hub + Propositions originals to thin redirects (after you confirm parity)

## Suggested direction for v10.348

1. **You verify v10.347 on localhost first** ← recommended
2. **v10.348 — Option E sub-batch 4: Competitor** (2 pages, similar shape to v10.347 — fast)
3. **v10.348 — Option E sub-batch 4: Platform/IT** (4 pages, similar shape to v10.345/v10.346)
4. **v10.348 — Convert originals to redirect stubs** (the cleanup batch, after parity confirmed)
5. **v10.348 — Continue original roadmap** (partnerships P&L / B-027 tail)

Which way?
