# Changelog — v10.345 Live Cockpit Consolidation (Option E sub-batch 1)

**Date:** 2026-05-12
**Phase:** 4 (thirtieth arc — first E batch in the harmonization plan)
**Audit:** 232/232 gates PASS = 100.0%
**Tests:** 10 new in `test_v10345_live_cockpit_consolidation.py`, all passing
**Page smoke:** 119/119 PASS at 100% (includes new `115_live_cockpits.py`)
**G162 Baseline:** 4022 — 39 consecutive zero-drift batches

---

## Your ask

> "option E" / "confirmed proceed with the best alternative"

First sub-batch of the module-consolidation arc. The Live Cockpits cluster — `pages/{109,110,111,112}_*_live.py` — was the smallest, lowest-risk consolidation candidate. Four parallel pages, identical 7-tab structure, all using the same `utils.cockpit_read` engine.

This is the structural answer to your original "front end is an entangled mess... I trust we have a solid strong base but we need to harmonize and let my front end project the backend as is."

## What v10.345 delivered

### One source of truth: `utils/live_cockpit_render.py`

1,829 lines consolidating the bodies of all 4 cockpit pages. Exports:

| Function | What it renders |
|---|---|
| `render_cims_cockpit(actor)` | 7 CIMS tabs (open work, instruction trace, recent capture, SLA risk, exception board, pending reviews, audit trail) |
| `render_treasury_cockpit(actor)` | 7 Treasury tabs (LCR/NSFR, IRRBB, FX positions, RWA, cash forecast, dashboard report) |
| `render_credit_cockpit(actor)` | 7 Credit tabs (loan pipeline, IFRS9 stages, NPL watchlist, admin, portfolio analytics, audit trail) |
| `render_compliance_cockpit(actor)` | 7 Compliance tabs (cases, AML alerts, sanctions, returns, CRA/training, audit trail) |

Cache helpers domain-prefixed (`_cims_cached_open_work`, `_treasury_cached_open_work`, etc.) so Streamlit's cache keys don't collide between domains.

### The 4 old pages: thin wrappers

| Page | Before | After |
|---|---|---|
| `109_cims_live.py` | 510 lines | **29 lines** |
| `110_treasury_live.py` | 466 lines | **26 lines** |
| `111_credit_live.py` | 463 lines | **26 lines** |
| `112_compliance_live.py` | 507 lines | **26 lines** |
| **Total** | **1,946** | **107** |

Each old page now:
- Honors the same `require_access(...)` gate (unchanged)
- Imports its `render_*_cockpit` from the helper module
- Reads `actor` from session_state
- Calls the render function

That's it. **94% reduction** on the 4 old pages. Same functionality — same data, same tabs, same access gating. The originals stay functional at their existing URLs so you can compare them tab-by-tab against the new consolidated page before deciding when to convert them to thin redirects.

### Consolidated entry point: `pages/115_live_cockpits.py`

149 lines. Composes via a domain selector:

```
┌────────────────────────────────────────────────────────────┐
│  📡 Live Cockpits                                          │
├────────────────────────────────────────────────────────────┤
│  Domain:  [ 🎛️ CIMS ]  [ 💰 Treasury ]  [ 📊 Credit ]  [ 🛡️ Compliance ]
├────────────────────────────────────────────────────────────┤
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐         │
│  │tab1│ │tab2│ │tab3│ │tab4│ │tab5│ │tab6│ │tab7│         │
│  └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘         │
│                                                            │
│   ... selected tab content ...                             │
└────────────────────────────────────────────────────────────┘
```

- **Segmented domain selector at top** (`st.segmented_control` with `st.radio` fallback for older Streamlit)
- **Per-domain access gating preserved.** Users only see the pills for domains they have access to. A user with only Treasury access sees just the Treasury pill — same access model as before, just unified.
- **Hard `require_access` enforcement when a domain is selected.** The unified page never relaxes access; the gate still raises/stops if a user somehow selects a domain they can't access.
- **Selection persists across reruns** via `session_state["live_cockpit_selected_key"]`.

### G232 audit gate

Locks the consolidation:
1. `utils/live_cockpit_render.py` exists with all 4 render functions
2. Each of the 4 old pages is ≤40 lines (thin wrapper)
3. Each old page imports its corresponding render function
4. `pages/115_live_cockpits.py` exists and imports all 4 render functions
5. All 5 pages smoke-test PASS (cross-checked with G231)

### Reversibility (Pattern M)

`data/_v10345_backups/` contains the pre-v10.345 bodies of all 4 original pages:
- `109_cims_live.py.before` (510 lines)
- `110_treasury_live.py.before` (466 lines)
- `111_credit_live.py.before` (463 lines)
- `112_compliance_live.py.before` (507 lines)

If anything in the consolidated view is wrong, restoring originals is `cp data/_v10345_backups/<name>.before pages/<name>`. No data lost.

## Architecture compliance fixes during build

Eleven audit gates failed initially after the consolidation — all of them checking for specific patterns in the OLD page bodies (`@st.cache_data(ttl=...)`, `audit_log(...)`, `audit_log_records`, `credit_portfolio_analytics`, `compliance_cra_training`, etc.). These were valid invariants but in the wrong file post-consolidation. Patched mechanically:

- **G186/G187/G191/G192** (live cockpit integration gates) — patched to concatenate `utils/live_cockpit_render.py` source onto the page source they examine. The invariants are now checked across page + helper.
- **G193/G195/G196/G199/G200** (composer wiring gates) — same patch applied to their `cockpit_src` / `src` readers.
- **G160 (page manifest)** — registered `115_live_cockpits.py` with full department + module_path + secondary_visibility entry.
- **G117 (engine hub coverage)** — added new "Tier 61 — Quality Gates & Harmonization (v10.342-v10.345)" to `ENGINE_HUB_TIERS` in `pages/7_admin.py`, registering all three of this session's harmonization engines:
  - `schema_validator` (v10.342)
  - `page_smoke` (v10.344)
  - `live_cockpit_render` (v10.345)

The Tier 61 registration is overdue — these tools have been quietly running the harmonization arc; they deserve a place in the engine hub alongside the business engines.

## What v10.345 did NOT do

- **Did not delete any of the 4 original cockpit pages.** They become deletion candidates in v10.346 after you confirm parity on localhost.
- **Did not modify `utils/cockpit_read.py`** — the shared engine the 4 cockpits already used. Same engine, same data feeds, just rerouted through `live_cockpit_render`.
- **Did not change access gating.** Each domain still gates exactly as before. The unified page only displays pills the user can access.
- **Did not add nested tabs.** Top-level is the domain selector; per-domain is the same 7-tab layout the originals had.

## Pattern S formalised

> **Page consolidation pattern.** When N pages share a parallel structure:
> 1. Inventory every tab / metric / action — confirm with user before code
> 2. Extract page bodies into a helper module with one render_*(actor) function per domain
> 3. Refactor each old page to a thin wrapper that calls its helper
> 4. Build a new entry point that composes the helpers via a selector
> 5. Old pages stay functional alongside until user confirms parity on localhost
> 6. Originals → thin redirect stubs in a follow-up batch
> 7. Audit gate locks the new architecture

## Verified outcome

| Metric | Before → After v10.345 |
|---|---|
| Audit gates | 231 → **232** (G232 added) |
| Page smoke coverage | 118 → **119 pages (100% PASS)** |
| Old pages line count | 1,946 → **107** (-94%) |
| New helper module | 0 → **1,829 lines** (single source of truth) |
| New entry point | 0 → **149 lines** (consolidated) |
| Engine hub coverage (G117) | 94.9% → **95.4%** (Tier 61 added) |
| New audit gate | G231 → **G232** |
| Backups | n/a → **4 originals preserved** |
| G162 baseline | 4022 (39 consecutive zero-drift batches) |

## Files changed

| File | Change |
|---|---|
| `utils/live_cockpit_render.py` | NEW — 1,829 lines, single source of truth for 4 render functions |
| `pages/109_cims_live.py` | 510 → 29 lines (thin wrapper) |
| `pages/110_treasury_live.py` | 466 → 26 lines (thin wrapper) |
| `pages/111_credit_live.py` | 463 → 26 lines (thin wrapper) |
| `pages/112_compliance_live.py` | 507 → 26 lines (thin wrapper) |
| `pages/115_live_cockpits.py` | NEW — 149 lines, consolidated entry |
| `pages/7_admin.py` | New "Tier 61 — Quality Gates & Harmonization" entry in ENGINE_HUB_TIERS |
| `pages/_manifest.json` | Registered `115_live_cockpits.py` |
| `scripts/audit.py` | New gate G232 + patches to G186/G187/G191/G192/G193/G195/G196/G199/G200 reading helper module |
| `scripts/build_live_cockpit_render.py` | NEW — one-shot generator (preserved for repeatability) |
| `scripts/verify_local_state.py` | Extended to 51 checks across v10.336-v10.345 |
| `data/_v10345_backups/*.before` | Pre-v10.345 page bodies preserved (Pattern M) |
| `tests/integration/test_v10345_live_cockpit_consolidation.py` | NEW — 10 tests |

## Backlog status

| ID | Status |
|---|---|
| B-009 – B-018 | Open |
| B-027 (tail) | Mostly closed |
| B-028, B-029 | Open |
| B-030, B-034 | Closed |
| B-031, B-032, B-033, B-035, B-036, B-037, B-038 | Open |
| B-039 (page schema drift) | Closed by G231 + G232 |
| B-040 | Closed |
| B-041 | Open (validate_before_save in more producers) |
| B-042, B-043 | Documented (Option E divergences) |
| B-044 NEW (Live Cockpits: old pages → thin redirects) | Pending your localhost confirmation |
| B-045 NEW (Option E sub-batch 2 candidates) | Open |

## Suggested next direction

Five candidates for v10.346 (E continues, or pause):

1. **You verify v10.345 on localhost first** ← recommended
2. **v10.346 — Option E sub-batch 2: Finance hub** — `9_sbu` + `114_sbu_drilldown` + `10_opex` + `52_mgmt_accounts` → single Finance module. Same pattern as Live Cockpits.
3. **v10.346 — Option E sub-batch 2: Propositions module** — `27_propositions` + `92_propositions_workbench` → one Propositions module. Smaller, even lower risk.
4. **v10.346 — Convert Live Cockpit originals to thin redirects** — once you've used `115_live_cockpits.py` on localhost and confirmed parity, this is the cleanup batch.
5. **v10.346 — Continue original roadmap** — partnerships P&L / Strategic Initiative engine / B-027 tail.

My honest recommendation: **option 1 — verify on localhost first.** v10.345 is the first E batch where you can SEE the consolidation. Better to confirm the unified page works for you, the 4 originals still work, and access gating behaves correctly before extending the pattern to other clusters.

Which way?
