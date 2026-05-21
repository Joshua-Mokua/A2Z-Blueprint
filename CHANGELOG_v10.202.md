# CHANGELOG v10.202 — First cockpit absorption (Treasury Arc → 25_treasury.py)

**Date:** 2026-05-06
**Theme:** First cockpit absorption batch under the
v10.196.1 architectural cleanup schedule. Folds
`26_treasury_arc_cockpit.py` into `25_treasury.py` as a 4th
top-level "🤖 Arc Engines" tab containing 7 nested sub-tabs. Refactors
G151 from location-based to manifest-aware behavior-based. Deletes
the cockpit file. Manifest drops from 108 → 107 pages. Audit holds at
**160/160 PASS**.

## What v10.202 ships

### 1. `pages/25_treasury.py` — absorbed Arc Engines as 4th top-level tab

Treasury page goes from 3 → 4 top-level tabs (within G4's 7-tab cap):

```
📊 Overview        💼 Products       ⚖️ Risk & Control       🤖 Arc Engines  ← NEW
```

Inside the new "🤖 Arc Engines" tab, 7 nested sub-tabs reproduce the
former cockpit's structure:

```
📊 Dashboard           — TreasuryIntelligenceEngine + TreasuryDashboardEngine
💧 Liquidity & ALM      — TreasuryALMEngine + LiquidityRiskEngine + LiquidityStressEngine
💰 Products             — TreasuryProductsEngine
🤖 Agents               — AgentOrchestrator
🔌 Connectivity         — TreasuryConnectivityEngine
🌐 Digital & Climate    — DigitalAssetTreasuryEngine + ClimateTreasuryLimitsEngine
🕌 Islamic & Unified    — IslamicTreasuryEngine + UnifiedTreasuryPlatform
```

All 12 engines (ENH-231..240, ENH-LR-001, ENH-TRS-R1..R6, CBK-PG-05-LCR)
preserved. `@st.cache_resource` engine instantiation moved into the
target page. Read-only display preserved; state-mutating workflows
continue to go through `utils/api_treasury.py` FastAPI endpoints.

### 2. `scripts/audit.py` — G151 refactored to manifest-aware

G151 (treasury_arc_ui_integrated, shipped v10.155) was the second
location-locked closure gate that needed manifest-aware refactoring
(G149 was the first, refactored in v10.199). Original implementation
required `pages/26_treasury_arc_cockpit.py` to exist and contain all 12
engine class references.

Refactored to **behavior-based**: scan all non-deprecated pages in the
`treasury_alm` department (resolved via the manifest), concatenate
their text, verify all 12 engine classes are referenced somewhere in
that combined text. Same discipline (Treasury arc engines must be
UI-integrated) but location-independent — engine references can move
within the department without breaking the gate.

This is the prerequisite refactor v10.196 Section 5 specified before
this cockpit absorption could ship. The same pattern will apply to
G130 (Strategy), G132 (Compliance), G133 (Legal), G134 (Resource
Optimization), G140 (Risk), G141 (Credit Governance), G142 (Revenue
Assurance), G143 (Finance), G144 (Trade Finance), G145 (ML Governance),
G146 (Integration), G147 (Product) when those cockpits are absorbed
in subsequent batches.

### 3. `pages/_manifest.json` — cockpit entry removed

The manifest entry for `26_treasury_arc_cockpit.py` deleted. Manifest
goes 108 → 107 pages, 13 → 12 deprecated cockpits.

### 4. `pages/26_treasury_arc_cockpit.py` — DELETED

**⚠️ The cockpit file must be manually deleted from your local
working tree when applying this zip.** Zips deliver added/modified
files but cannot express deletions. The deletion is required for the
audit to pass — G160 enforces "every page on disk has a manifest
entry" and the manifest entry is removed. Either:
1. Delete `pages/26_treasury_arc_cockpit.py` manually, OR
2. Apply the zip then run: `rm pages/26_treasury_arc_cockpit.py`

After the deletion, run `python scripts/audit.py` to verify
160/160 PASS.

## Files changed (3 modified + 1 deletion)

```
pages/25_treasury.py              MOD  +291 lines  (779 → 1070)
                                       (4th top-level tab + 7 nested sub-tabs)
scripts/audit.py                  MOD  +44 lines net  (G151 refactor)
pages/_manifest.json              MOD  -16 lines  (cockpit entry removed)
pages/26_treasury_arc_cockpit.py  DEL  -407 lines  (manual deletion required — see above)
```

Net cockpit absorption: -407 (cockpit) + +291 (target) - 16 (manifest)
= -132 lines net code reduction. The reduction comes from elimination
of the cockpit's preamble + duplicate engine import + standalone
@st.cache_resource decorator + standalone require_access call —
content that the target page already provides.

## Audit

```
Before (v10.201): Score: 160/160 gates = 100.0% — PASS
After  (v10.202): Score: 160/160 gates = 100.0% — PASS
```

Trajectory through this batch:
1. Add 4th top-level tab to 25_treasury.py: 160/160 PASS (cockpit still
   exists, G151 still passes via the cockpit text)
2. Append nested sub-tabs to section[3] body: 160/160 PASS
3. Refactor G151 to manifest-aware: 160/160 PASS (still finds engines —
   now searches both 25_treasury and the cockpit, both currently exist)
4. Delete cockpit file + remove manifest entry: 160/160 PASS (G151 finds
   all engines in 25_treasury alone; G160 sees 107 pages on disk and 107
   manifest entries; G149 sees 12/12 cockpits registered)

## What gets visibly preserved for users

A Treasury Manager who used to navigate via the sidebar to "Treasury
Arc Cockpit" (separate sidebar entry, 26_treasury_arc_cockpit.py) now
navigates to "Treasury Dashboard" (25_treasury.py) and clicks the
"🤖 Arc Engines" top-level tab. Same content, fewer sidebar entries.

The 4-tab structure (Overview, Products, Risk & Control, Arc Engines)
groups Treasury work by operator scope:
- **Overview / Products / Risk & Control** — daily operational pages
  (FD ratification, FX dealing, money market, government securities,
  ALM ratios, limits & compliance) used by dealers and treasury
  operations
- **Arc Engines** — strategic/board-level intelligence and rollups
  used by Treasurer, CFO, ALCO members for monthly/quarterly
  reporting

Same content, better navigation discoverability — the cockpit was
previously a separate page that operators had to discover and remember;
now it's a tab on the page they already use daily.

## Cockpit absorption schedule

13 → 12 cockpits remaining after v10.202. Per v10.197 manifest's
deprecation_target_page metadata:

| Cockpit | Target | Closure gate to refactor | Status |
|---|---|---|---|
| ~~26_treasury_arc_cockpit.py~~ | ~~25_treasury.py~~ | ~~G151~~ | **✅ v10.202** |
| 15_strategy_arc_cockpit.py | 83_strategy.py | G159 | pending |
| 16_product_arc_cockpit.py | 5_products.py | G148 | pending |
| 27_compliance_arc_cockpit.py | 24_compliance.py | TBD | pending |
| 28_legal_arc_cockpit.py | 26_legal.py | TBD | pending |
| 29_resource_optimization_cockpit.py | 10_opex.py | G157 | pending |
| 93_risk_arc_cockpit.py | 35_stress_testing.py | TBD | pending |
| 94_credit_governance_cockpit.py | 22_credit_analysis.py | TBD | pending |
| 95_revenue_assurance_cockpit.py | 29_revenue_assurance.py | TBD | pending |
| 96_finance_arc_cockpit.py | 52_mgmt_accounts.py | TBD | pending |
| 97_trade_finance_arc_cockpit.py | 46_trade_finance.py | TBD | pending |
| 98_ml_governance_arc_cockpit.py | 91_systems_view.py | TBD | pending |
| 99_integration_cockpit.py | 91_systems_view.py | TBD | pending |

At ~1 cockpit per batch, target completion v10.214. v10.250 buffer
allows for harder consolidations (e.g. ML Governance + Integration
both target 91_systems_view.py — second absorption may need to sequence
around the first).

## Strategic narrative — the absorption pattern is now reproducible

This batch demonstrates the canonical 5-step pattern for cockpit
absorption that all 12 remaining absorptions will follow:

1. **Add target tab to target page** — non-destructive; cockpit still
   works; audit clean
2. **Append cockpit content as nested sub-tabs** — non-destructive;
   both render the same content; audit clean
3. **Refactor closure gate to manifest-aware behavior-based** — gate
   now checks "engines integrated somewhere in dept" not "engines in
   specific file"; audit clean
4. **Delete cockpit file + remove manifest entry** — single atomic
   change; G160 sees both fewer pages on disk and fewer manifest
   entries (matched); G151 finds engines in target page alone; audit
   clean
5. **Communicate deletion in CHANGELOG** — zips can't express
   deletions; user manually removes the file when applying

The pattern is now codified. Each subsequent cockpit absorption
follows the same 5 steps. The first one took analysis (figuring out
which closure gate locks each cockpit, determining the right tab
structure, sequencing the refactors). The next 12 are mechanical.

## Honest acknowledgements

1. **Cockpit deletion requires a manual step.** Zips deliver added/
   modified files but cannot express deletions. The CHANGELOG calls
   this out prominently. After applying the zip, the user must
   `rm pages/26_treasury_arc_cockpit.py` then re-run audit. Without
   the deletion, audit fails G160 (cockpit file on disk has no manifest
   entry). This is a known limitation of the zip-based delivery model.

2. **The "🤖 Arc Engines" tab uses lazy imports** wrapped in
   try/except. If any treasury_*.py engine module has an import error
   (e.g. missing dependency), the rest of the Treasury page still
   renders — only the Arc Engines tab shows "Arc engines unavailable".
   This is a small behavioral improvement over the cockpit, which would
   fail to load entirely on engine import error.

3. **`@st.cache_resource _get_arc_engines()` is now defined inside
   the section[3] body.** This means engines are only instantiated
   when the user clicks the "🤖 Arc Engines" tab. Previously
   (in the cockpit) they were instantiated on cockpit page load. Net
   effect: faster page load for Treasury Manager who only uses the
   Overview tab; same speed for those who navigate to Arc Engines.

4. **The cockpit's footer audit_log call is preserved** with the
   action renamed from `treasury_arc_cockpit.view` to
   `treasury_arc_engines.view`. Existing audit-trail consumers that
   filter on the action name will see a discontinuity at v10.202.
   This is intentional: the action accurately describes the
   integration point now (engines tab on Treasury page, not standalone
   cockpit). If audit-trail consumers need the old name, they can
   match both `treasury_arc_cockpit.view` (historical, pre-v10.202)
   and `treasury_arc_engines.view` (current, v10.202+).

5. **The G151 refactor scans page text via concatenation.** All
   non-deprecated pages in the `treasury_alm` department are read,
   concatenated, then searched for the 12 engine class names. This
   is simpler than per-page individual checks and gives the right
   answer ("engines are integrated somewhere in dept"). Cost: ~30ms
   per audit run for the I/O. Acceptable.

6. **G149 still works correctly** — it counts non-deprecated
   manifest entries with `*_cockpit.py` filename pattern. After the
   manifest entry deletion + file deletion, the count drops by 1 on
   both sides (12/12 from 13/13). The gate was already manifest-aware
   from v10.199.

7. **The 5-step pattern requires investigation per cockpit.** I had
   to figure out:
    - Which closure gate locks each cockpit (search audit.py)
    - What engines/methods that gate checks
    - What tab structure the cockpit uses
    - How to integrate into the target page without exceeding G4's
      7-tab limit
   For the next 12 absorptions, this investigation is required again
   per cockpit. A future enhancement could be to encode the engines/
   gates per cockpit in the manifest itself (`expected_engines: [...]`
   on cockpit entries) — but that's premature optimization until
   pattern stabilizes.

8. **The cockpit's standalone `st.set_page_config` call is dropped.**
   25_treasury.py already has its own page config. The Arc Engines tab
   inherits the parent page's title and layout. Functionally identical.

9. **Page-number collision continues to exist.** `15_cbs.py`,
   `15_optimize.py`, `15_strategy_arc_cockpit.py` all still claim slot
   15. v10.202 didn't touch those. The strategy_arc cockpit is a future
   absorption candidate (target: 83_strategy.py). When that absorption
   ships, slot 15 will be claimed by only `15_cbs.py` and `15_optimize.py`
   — still 2-way collision but less than 3-way. Resolution of the
   remaining 2-way collisions (renaming files) is a separate concern;
   the manifest's `module_path` is the routing authority post-v10.199
   so the numeric collisions are cosmetic.

10. **No tests for the absorbed Arc Engines tab.** Same as the
    cockpit it replaced — the 12 engines are tested via the API
    endpoints in `tests/test_api_treasury.py` (which still pass since
    the API surface didn't change). UI rendering is verified by the
    audit script's syntactic checks (G1) and tab-count check (G4),
    plus the engine-reference check in G151. Functional UI testing is
    Joshua's manual review.

11. **The 5-step pattern produces a net code reduction.** v10.202
    reduces total LOC by ~132 lines (cockpit -407, target +291,
    manifest -16). Across 12 remaining absorptions at similar ratios,
    expected total reduction ≈ 1500-1800 lines. Less code, fewer
    maintenance points, same functionality.

12. **12 consecutive clean batches in this session** — v10.193 through
    v10.202 (10 code batches + 2 advisory reviews). The architectural
    reorganization sub-campaign is closed (v10.197-v10.201) and the
    cockpit absorption sub-campaign is now active (v10.202+). Each
    sub-campaign has its own characteristic pattern; both share the
    discipline of single-purpose batches with audit-clean before/after
    and honest acknowledgements at the end.

## Next batch options

1. **v10.203 — Strategy Arc absorption.** Same 5-step pattern, target
   `83_strategy.py`, refactor G159. ~150 lines net change. The
   alphabetic-by-cockpit-name order would naturally pick this next
   (15_strategy_arc < 16_product_arc < 27_compliance_arc < ...).
2. **v10.203 — Page migration to dotted form (Treasury department).**
   Now that Treasury has the absorbed Arc Engines tab and is the
   "completed" department, migrate its 7 (post-v10.202) pages from
   `require_access("treasury")` to `require_access("treasury_alm.alm")`
   etc. ~30 lines per page × 7 pages = ~210 lines. Validates the
   dotted-path access end-to-end.
3. **v10.203 — Return to deferred platform items.** PG migration,
   React SPA, React Native, etc.

I'd lean toward **option 1** (continuous improvement of cockpit
absorption) since the pattern is now mechanical and each absorption
ratchets the platform's structural quality. But all three are
reasonable.
