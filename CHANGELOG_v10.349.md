# Changelog — v10.349 Platform Hub Consolidation (Option E sub-batch 5)

**Date:** 2026-05-12
**Phase:** 4 (thirty-fourth arc — fifth and final 4-page E batch)
**Audit:** 236/236 gates PASS = 100.0%
**Tests:** 12 new in `test_v10349_platform_hub_consolidation.py`, all passing
**Page smoke:** 123/123 PASS at 100%
**Verifier:** 91/91 checks pass on a clean extract
**G162 Baseline:** 4022 (43 consecutive zero-drift batches)

---

## Your ask

> "v10.349 — Option E sub-batch 5: Platform/IT"

Fifth E batch — and the **last 4-page consolidation cluster**. Same Pattern S that's now been proven across:

- v10.345 Live Cockpits (4 pages)
- v10.346 Finance Hub (4 pages)
- v10.347 Propositions Hub (2 pages)
- v10.348 Competitor Hub (2 pages)

After v10.349, all the remaining clusters Joshua named in the v10.345 inventory are consolidated. Five separate fronts of front-end clutter, all collapsed into unified entries with helpers as single sources of truth.

## What v10.349 delivered

### Helper module: `utils/platform_hub_render.py` (4,326 lines)

The largest helper yet — Platform/IT has the deepest content. Single source of truth for 4 render functions:

| Function | Source page | What it renders |
|---|---|---|
| `render_systems_view(actor)` | `91_systems_view.py` (2,324 lines) | The "football team" page — 6 sections making the systems layer (Charter v7.0) visible. Meta-page surfacing how A2Z works as a system. Audience: Exec/MD. |
| `render_it_digital_pt1(actor)` | `96_it_digital_pt1.py` (474 lines) | Standards #291-#295 across 5 engines: ITSM Incidents, ITSM Changes & Assets, Cloud Architecture, Observability (SLI/SLO), Disaster Recovery, API Gateway, Knowledge Base. Audience: CTO/CIO/IT ops/SRE/security/compliance. |
| `render_it_digital_pt2(actor)` | `97_it_digital_pt2.py` (1,099 lines) | Standards #296-#300 across 5 engines: Encryption Keys, Secrets & PII, CI/CD Pipelines, Tenants & Branding, Feature Flags, Digital Channels & Sessions, Compliance & Certifications. Audience: CISO/CTO/CIO/security engineering/compliance/audit. |
| `render_platform_health(actor)` | `98_platform_health.py` (455 lines) | Operator-facing single-page health view. Runs 3 diagnostics live: audit gates, structural checks, engine self-tests. Plus inventory tabs for standards + scenarios. Audience: Operators (BAs/auditors/IT manager). |

Domain-namespaced cache helpers as in earlier batches, build script auto-rewrites `pages._*` imports to `utils.page_*` canonical paths.

### Thin wrapper pages

| Page | Before → After | Audience |
|---|---|---|
| `91_systems_view.py` | 2,324 → **27** lines | Exec/MD — systems layer |
| `96_it_digital_pt1.py` | 474 → **26** lines | CTO/CIO/SRE — Standards #291-#295 |
| `97_it_digital_pt2.py` | 1,099 → **26** lines | CISO/Security — Standards #296-#300 |
| `98_platform_health.py` | 455 → **28** lines | Operators — live diagnostics |
| **Total** | **4,352 → 107 lines (-98%)** | |

Biggest reduction percentage of any E batch so far. `91_systems_view.py` alone was 2,324 lines — bigger than all 4 Live Cockpit originals combined.

### Consolidated entry: `pages/119_platform_hub.py` (153 lines)

Segmented area selector at top, four pills (Systems View / IT Digital Pt 1 / IT Digital Pt 2 / Platform Health), per-area `require_access` gating preserved. Users only see the pills they can access.

### Access model — 4 different audiences preserved

| Area | Permission | Audience |
|---|---|---|
| 🏛️ Systems View | `it_platform.systems_view` | Exec, MD |
| 🔧 IT Digital Pt 1 | `it_platform.it_digital_pt1` | CTO, CIO, SRE, IT ops |
| 🔐 IT Digital Pt 2 | `it_platform.it_digital_pt2` | CISO, security, compliance |
| 💚 Platform Health | `it_platform.platform_health` (with legacy `platform_health` fallback) | Operators, BAs, auditors |

The `98_platform_health.py` wrapper preserves the **legacy + dotted dual-permission pattern**: it tries `require_access("platform_health", silent=True)` first (legacy), then falls through to `it_platform.platform_health` (dotted) if silent denied. Original behavior preserved exactly.

### Audit gate G236

Locks the consolidation:
1. `utils/platform_hub_render.py` exists with all 4 render functions
2. Each of the 4 old pages is ≤40 lines (thin wrapper)
3. Each old page imports its render function
4. `pages/119_platform_hub.py` exists and imports all 4 render functions
5. All 5 pages smoke-test PASS

### Reversibility (Pattern M)

`data/_v10349_backups/` contains the pre-v10.349 bodies of all 4 originals:
- `91_systems_view.py.before` (2,324 lines)
- `96_it_digital_pt1.py.before` (474 lines)
- `97_it_digital_pt2.py.before` (1,099 lines)
- `98_platform_health.py.before` (455 lines)

## What's been accomplished across the full Option E arc

Pattern S now proven across **5 clusters totalling 16 original pages collapsed to 5 unified entries**:

| Batch | Cluster | Pages | Lines reduced |
|---|---|---|---|
| v10.345 | Live Cockpits | 4 → 5 | 1,946 → 107 (**-94%**) |
| v10.346 | Finance Hub | 4 → 5 | 2,519 → 104 (**-96%**) |
| v10.347 | Propositions Hub | 2 → 3 | 955 → 52 (**-95%**) |
| v10.348 | Competitor Hub | 2 → 3 | 783 → 53 (**-93%**) |
| v10.349 | Platform Hub | 4 → 5 | 4,352 → 107 (**-98%**) |
| **Total** | **16 → 21** | | **10,555 → 423 lines (-96%)** |

10,555 lines of body code that was spread across 16 cluttered pages is now in 5 helper modules — single sources of truth, with audit gates locking each architecture in place. **96% net reduction** on the original pages. All 91 sub-tabs preserved across all 5 hubs.

## Files changed

| File | Change |
|---|---|
| `utils/platform_hub_render.py` | NEW — 4,326 lines, 4 render functions |
| `pages/91_systems_view.py` | 2,324 → 27 lines (thin wrapper) |
| `pages/96_it_digital_pt1.py` | 474 → 26 lines (thin wrapper) |
| `pages/97_it_digital_pt2.py` | 1,099 → 26 lines (thin wrapper) |
| `pages/98_platform_health.py` | 455 → 28 lines (thin wrapper, dual permission preserved) |
| `pages/119_platform_hub.py` | NEW — 153 lines, consolidated entry |
| `pages/7_admin.py` | Tier 65 + Tier 66 entries for Platform Hub + infrastructure engines |
| `pages/_manifest.json` | Registered `119_platform_hub.py` |
| `scripts/audit.py` | New gate G236 + patches to G117 (added platform_hub_render registration via Tier 65) |
| `scripts/build_platform_hub_render.py` | NEW — one-shot generator with `_PAGES_SHIM_MAP` |
| `scripts/verify_local_state.py` | Extended to 91 checks across v10.336-v10.349 |
| `data/_v10349_backups/*.before` | Pre-v10.349 bodies preserved (Pattern M) |
| `tests/integration/test_v10349_platform_hub_consolidation.py` | NEW — 12 tests |

## Verified outcome

| Metric | Before → After v10.349 |
|---|---|
| Audit gates | 235 → **236** (G236 added) |
| Page smoke coverage | 122 → **123 pages (100% PASS)** |
| Old pages line count | 4,352 → **107 lines** (-98%) |
| New helper module | 0 → **4,326 lines** (single source of truth) |
| New entry point | 0 → **153 lines** (consolidated) |
| Engine hub coverage (G117) | 95.4% → **95.5%** (platform_hub_render registered in Tier 65) |
| Verifier | 80 → **91 checks** |
| Total clusters consolidated | 4 → **5** (last 4-page cluster) |
| G162 baseline | 4022 (43 consecutive zero-drift batches) |

## Suggested direction for v10.350

Now that all 5 E clusters are consolidated, the E arc has three natural follow-ups:

1. **You verify v10.349 on localhost first** ← recommended (same as every E batch closer)
2. **v10.350 — Convert all consolidated originals to thin redirects** — the cleanup batch. All 16 originals currently stay alongside the unified hubs. After you've used the hubs enough to be sure of parity, this batch would redirect users from the originals to the appropriate hub area. ~150 lines of redirect code per old page.
3. **v10.350 — Continue original roadmap** — partnerships P&L, B-027 tail, Strategic Initiative engine. The E arc as a deliberate harmonization phase is closed; remaining work returns to feature delivery.
4. **v10.350 — Address the documented divergences** — `strategic_initiatives.rag_status` (Title vs UPPERCASE) and `kpi_library.kpis[].direction` (short vs long form). Both locked in schemas with all values allowed; consolidation would change consumer behavior, so was deferred from Option D.

My honest recommendation: **option 1 — verify on localhost first.** The full E arc is now in your hands — five unified entry points plus all originals still functional alongside. Best to confirm the unified view delivers what you need across all five clusters before deciding the next direction.

Which way?
