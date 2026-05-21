# Changelog — v10.331 Branch Ranking page

**Date:** 2026-05-12
**Phase:** 4 (seventeenth arc — branch ranking UI surface)
**Audit:** 221/221 gates PASS = 100.0%
**Tests:** 638/638 passing across 37 integration suites (8 new for v10.331)
**G162 Baseline:** 4022 — 26 consecutive zero-drift batches

---

## What shipped

Dedicated **Branch Ranking** page at `pages/113_branch_ranking.py`
surfacing the 94-branch BSC comparison view that was previously buried
inside cross-sell deepening (`pages/45_crosssell.py`).

This page is the demo deliverable for your earlier ask: a
sortable, drill-able branch ranking report using the BSC scorecard
that v10.329 created.

## The 7 tabs (G4-compliant)

### Tab 1 — Overall ranking
All 94 branches ranked by overall BSC score. Sortable by any KPI
column. Top quartile (≥75th pct) shown green, bottom quartile (≤25th
pct) shown red. Includes Rank, Branch Manager name, Area Manager,
Role (BM vs Senior BM), and all 11 surfaced KPIs.

### Tab 2 — By Area Manager
Area Managers ranked by mean branch score. Each AM expandable to
show their 9-10 branches and how each is performing. **Area Manager
BSC IS the aggregate of branches reporting to them** — this tab
makes that visible.

### Tab 3 — KPI heatmap
Top 30 branches × 11 KPIs as a heatmap. Green-to-red gradient where
appropriate (e.g. higher is better for PBT/NFI/CASA/audit) and
inverted for NPL Ratio + PAR (lower is better). Lets the MD spot
patterns: "Branch X dominates PBT but lags compliance."

### Tab 4 — Bottom-quartile attention
The 24 branches at the bottom 25%. Lists why each is there:
NPL ratio over 8%, audit score below 70, CASA below 55%. Aimed at
the Chief Retail review meeting: "Here are the 24 branches I want
in next week's intervention plan."

### Tab 5 — Trend
4-quarter trend of BM mean/min/max scores. Shows whether the network
is improving, declining, or holding. Line chart over Q3'25 → Q2'26.

### Tab 6 — KPI distribution
Mean/median/min/max/std for the key KPIs (PBT, NPL Ratio, PAR, CASA,
audit, CX) across the 94-branch network. Useful for setting next
quarter's targets — "median PBT is X, top decile is Y, set the BM
target at Z."

### Tab 7 — Drill-down
Pick a single Branch Manager. See their full 21-KPI scorecard plus
overall score, band, Role, and Area Manager. The "click into a branch"
view the MD reaches for when a name comes up in conversation.

## Demo path the page enables

```
1. MD opens cascade (3.37 overall)
2. Drill into Chief Retail (3.36)
3. Drill into Head of Branches (3.36)
4. See 10 Area Managers, spread 3.02 - 3.74
5. Click into AM 300004 (lowest, 3.02)
   → see their 10 branches
6. Click into Branch Ranking page → Tab 4 (bottom quartile)
   → see all 24 weakest branches across the bank
7. Identify common patterns: 9 have NPL > 8%, 6 have audit < 70
8. Decision: NPL task force for the 9; audit intervention for the 6
```

That's the BSC-from-Teller-to-MD story made operational.

## Configurability — currency-aware labels

Column labels like "PBT (KES M)" used to be hardcoded. Now they're
sourced via `get_currency()` from `org_config.json`:

```python
try:
    _CCY = get_currency()
except Exception:
    _CCY = ""
if _CCY:
    df = df.rename(columns={
        "PBT (M)": f"PBT ({_CCY} M)",
        "Total NFI (M)": f"Total NFI ({_CCY} M)",
    })
```

For Ecobank Kenya the label renders "PBT (KES M)". For a Tanzania
deployment, just change `currency_symbol` in `org_config.json` to
"TZS" and the column relabels.

This was a real fix — initial draft had hardcoded "KES M" strings
which tripped G162 (tenant_identity_hardcoding). Caught by audit
and fixed before ship.

## Architectural compliance

| Gate | Check | Status |
|------|-------|--------|
| G2 | No direct file I/O — uses `db.load_json` | ✓ |
| G4 | ≤7 tabs per page | ✓ (exactly 7) |
| G130 | UI integration page for cascade arc | ✓ |
| G160 | 7-field manifest entry | ✓ |
| G162 | No hardcoded tenant strings | ✓ (zero "KES" literals) |
| G220 | Branch Manager data source | ✓ (consumes v10.329 generator output) |
| G221 | Canonical retail chain | ✓ (renders v10.330 hierarchy) |

## Files changed

| File | Change |
|------|--------|
| `pages/113_branch_ranking.py` | NEW — 7-tab branch ranking page (385 lines) |
| `pages/_manifest.json` | NEW entry for 113_branch_ranking.py with 7 G160 fields |
| `tests/integration/test_v10331_branch_ranking.py` | NEW — 8 tests across 3 sections |

## Platform state

| Metric | v10.330 → v10.331 |
|--------|-------------------|
| Audit gates | 221 → **221** (unchanged — no new gate, this is UI consumption) |
| Integration test suites | 36 → **37** |
| Tests passing | 630 → **638** |
| Total pages registered | 116 → **117** |
| Branch ranking UI surface | buried in 45_crosssell | **dedicated page** |
| Currency configurability | partial | **complete for new page** |
| G162 baseline | 4022 (26 consecutive zero-drift batches) |

## Honest scope notes

1. **No new audit gate.** v10.331 surfaces existing v10.329/v10.330
   data into a UI page. The gate to block regressions on this page
   would either be UI-render (currently no headless-render harness)
   or content-check (already covered by integration tests). Logged as
   a defer rather than adding a thin gate.

2. **No new BSC data.** All values shown on this page come from the
   existing `cascade_scores_*.json` and `bsc_actuals_*.json` files.
   The page is read-only.

3. **Tab 5 Trend uses up to 4 quarters.** If you add Q3 2026 actuals
   later, the trend tab will automatically pick them up via
   `periods_available` glob.

4. **Tab 4 bottom-quartile rules are hardcoded thresholds** (NPL > 8,
   PAR > 6, Audit < 70, CASA < 55). Could be moved to org_config.json
   for v10.332 — for now matches CBK and internal review thresholds
   for Tier-2 Kenya banks.

## Backlog status

| ID | Status |
|----|--------|
| B-023 | Open — Credit Monitoring under Analysis vs Collections |
| B-024 | Open — Full MD rollups exceeds timeout (perf) |
| B-025 | Open — Hierarchy layer order hardcoded; admin config covers role-mapping not layer-order |
| B-026 | NEW — Bottom-quartile thresholds hardcoded in branch ranking page; should be org_config-driven |
| B-009, B-010, B-011, B-014-B-021 | Unchanged |

## Suggested next batches

With cascade story end-to-end + branch ranking UI shipped, demo-day
priorities (<1 week):

1. **v10.332 — Demo dry-run + screenshots** — walk the cascade as MD,
   capture screenshots, prepare Ecobank pitch talking points
2. **v10.332 — Performance optimization for full rollups (B-024)** —
   so MD subtree rollup finishes in <2 min instead of timing out
3. **v10.332 — Production-readiness pass** — review `_v10*_synthetic`
   tags and document filter strategy for prod deployment

What's the priority?
