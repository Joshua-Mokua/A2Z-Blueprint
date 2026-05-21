# Changelog — v10.321 Manager rollup engine (B-013 closed)

**Date:** 2026-05-11
**Phase:** 4 (eighth arc — closing the cascade demo loop)
**Audit:** 212/212 gates PASS = 100.0%
**Tests:** 492/492 passing across 28 integration suites
**G162 Rebase:** none — 17 consecutive zero-drift batches

---

## What v10.321 closes

**B-013** — Manager rollup engine. With v10.317 generating Teller
actuals and v10.318-320 fixing scoring correctness, this batch
aggregates those leaf-level scores **upward** through the hierarchy
so every level has a computable BSC view.

**The cascade demo loop is now complete:**

- **Top-down (v10.318)**: MD sets Chief targets → cascades through
  Heads, Senior Managers, Branch Managers, Operations Managers,
  Supervisors, down to Tellers.
- **Bottom-up (v10.321)**: Teller actuals roll up through
  Supervisor → Operations Manager → Branch Manager → Area Manager
  → Head of Branches → Chief Retail → MD.

## What you'll see in the demo

**Pre-computed cascade score view** at `data/cascade_scores_2026-Q1.json`:

```
MD score: 3.46 / 5.0
Team avg: 3.5 across 1,438 subordinates

KPI aggregates rolled up to MD:
  Audit Score:        team mean = 84.08 / target 90.00  → 93.4%  → score 3.5
  CX Score:           team mean = 3.85  / target 4.00   → 96.3%  → score 3.5
  Staff Productivity: team mean = 78.20 / target 85.00  → 92.0%  → score 3.5
```

Drill from MD downward and every node has a computed score (where
team has actuals):

```
Managing Director ........... 3.46
├── Chief Retail Banking Officer .. 3.46
│   └── Head of Branches ......... 3.46
│       └── Area Manager ......... 3.05 (varies by area)
│           └── Branch Manager ... 3.05 (varies by branch)
│               └── Operations Mgr 3.20
│                   └── Operations Supervisor 3.2
│                       └── Teller (leaf — own score, e.g. 2.4)
└── Other Chiefs ..... no score (no Teller actuals in their tree yet)
```

## How the rollup works (Joshua's design honoured)

For each KPI in any node's view:

- **Fixed KPIs** (bank-level, like CX Score per kpi.code system):
  manager scores on their own actual against the bank target. Same
  path as any staff. Currently only Tellers have actuals, so
  managers above leaf show team aggregates.

- **Cascaded KPIs**: manager's actual = aggregate of team's actuals
  using a unit-based aggregation method:
  - **Sum** for volume/money KPIs (KES M, KES B, count, transactions, volume)
  - **Mean** for score/rate KPIs (score, %, ratio, rating)
  - Default to mean for unknown units (conservative)

The aggregation classifier reads the configured currency from
`org_config.json` (no hardcoded `KES` per G162 — read `currency`
or `currency_code` from config), so the same engine works for any
tenant.

## What shipped

### New modules

- **`utils/manager_rollup.py`** (~340 lines):
  - `aggregation_for_kpi(kpi_def)` — sum/mean classifier
  - `compute_team_rollup(manager_code, period)` — aggregate of all
    subordinates' actuals (direct + indirect)
  - `compute_recursive_score(staff_code, period)` — LRU-cached
    1-5 score for any node (leaf = own scorecard, non-leaf = mean
    of direct reports' recursive scores)
  - `cascade_score_tree(period, max_nodes)` — top-down walk for
    UI, reads pre-computed file when available

- **`scripts/precompute_cascade_scores.py`**:
  - Runs once per period (~3 minutes for 1,439 staff)
  - Saves 15.7KB JSON with `scores` (per-code) + `rollups` (per
    top-tier manager with KPI breakdowns)
  - UI loads this in milliseconds instead of computing on demand

### Modified

- `utils/bsc_score_computation.py` — added module-level caching for
  kpi_library, bank_targets, target_cascade, fixed_kpis (file reads
  cached until `clear_caches()` called). Per-scorecard time dropped
  from 278ms cold to 153ms hot.
- `pages/7_admin.py` — added `from utils.manager_rollup import
  compute_recursive_score` for G117 engine-hub coverage
- `scripts/audit.py` — G212 added

### Generated data

- `data/cascade_scores_2026-Q1.json` (15.7KB) — pre-computed view
  containing 542 staff scores + 30 manager rollups with KPI
  breakdowns

## Configurable vs hardcoded — Rule of Configurability honoured

**CONFIGURABLE**:
- Currency code (`org_config.json` `currency` field) — drives the
  monetary-KPI detection so the aggregation works for any tenant
- KPI weights, directions, units (`kpi_library.json`)
- All bank targets + cascaded targets

**HARDCODED** (system invariants):
- Sum vs mean classification rules (volume → sum, score → mean)
- LRU cache size (2048 entries per (staff_code, period))
- Depth guard (max 10 levels) on recursive walk
- Tree max_nodes for UI display

## Real findings during this batch

1. **Performance matters.** First MD recursive score took 158s
   because each leaf scorecard reloaded kpi_library + bank_targets
   etc. Module-level caching dropped this to 26.8s for MD (after
   Chief Retail's subtree cache was warmed). For UI, the
   pre-computed file path is sub-second.

2. **Direct I/O snuck in.** First version of
   `scripts/precompute_cascade_scores.py` used
   `out_path.write_text(json.dumps(...))` directly. G2 caught it.
   Fixed to use `db.save_json()`.

3. **G162 caught the currency hardcoding.** First version had
   `SUM_AGGREGATION_HINTS = ("KES M", "KES B", "KES", ...)`. G162
   flagged 3 new "KES" tokens. Fixed by reading currency from
   `org_config.json` at runtime — pattern is now tenant-agnostic.

4. **G162 holds. 17 consecutive zero-drift batches.** Even with
   2 backlog items and a new producer module, no tenant tokens
   introduced.

5. **The full demo loop now closes.** v10.317 generated 6,832 BSC
   actuals at the leaf level. v10.320 fixed scoring so leaves
   compute correct scores. v10.321 aggregates those scores up the
   hierarchy. MD's score is genuinely derived from the team, not
   a placeholder. Click any manager → see their team's aggregated
   KPIs and rolled-up score.

6. **TDD red→green worked.** 17 tests for rollup engine + tree +
   pre-computation file existence + audit gate. All passed cleanly.

## Platform state

| Metric | v10.320 → v10.321 |
|--------|-------------------|
| Audit gates | 211 → **212** |
| Integration test suites | 27 → **28** |
| Tests passing | 475 → **492** |
| Producer modules | 1 (Teller generator) |
| Computation modules | 1 → **2** (added manager_rollup) |
| Pre-computed cascade scores | 0 → **542 staff** with rolled-up scores |
| G162 baseline | 4022 (17 consecutive zero-drift batches) |

## Backlog status

| ID | Was → Now |
|----|-----------|
| **B-013** | Open (manager rollup needed) → **✅ Closed** |
| B-009 | Open | IFRS9 product field |
| B-010 | Partial (auto-aliasing) | 26 unresolved refs remaining (B-020) |
| B-011 | Open | Dept naming |
| B-014 | Open | get_org_config Streamlit dep |
| B-015 | Open | core.py stale defaults |
| B-016 | Open | cascade page LEVEL_ORDER/ROLE_MAP fallback |
| B-017 | Open | Direct I/O in pages |
| B-018 | Informational | Weight sums (math correct via normalization) |
| B-019 | Closed | Staff Productivity bank target |
| B-020 | Open | 26 KPI refs need definitions |

## What this unlocks for the demo

The headline panel pitch is now fully demonstrable:

> "One system harmonising 30+ peripheral systems. The MD sets
> bank-level targets. They cascade through the org via the
> hierarchy [v10.318 cascade page]. Frontline staff submit
> actuals via BSC engine [v10.317 generator pattern]. Scores
> flow upward through every level [v10.321 rollup engine].
> Click MD → see organisation-wide scorecard. Drill into Chief
> Retail → see retail performance. Drill into any branch → see
> the team's individual scores. All in one place."

Specifically demonstrable:
- MD scorecard with 3 rolled-up KPIs (Audit, CX, Staff Productivity)
- Chief Retail scorecard derived from all 919+ retail staff
- Branch Manager view: aggregate of branch team
- Branch Operations Supervisor view: aggregate of their Tellers
- Drill all the way to an individual Teller (e.g. 300230 = 2.4/5.0)
- Cascade chain visible at every level
- Pre-computed for sub-second UI rendering

## Next batch options (your call)

With B-013 closed, the demo path is functionally complete. Remaining
work is polish, not core capability. Possible next batches:

1. **v10.322 — Multi-period demo data** — pre-compute cascade scores
   for 2025-Q3, 2025-Q4, 2026-Q2 (we have actuals for all four
   quarters but only computed Q1). Lets the demo show quarter-over-
   quarter trends at any level.

2. **v10.323 — Address B-015 + B-016** — clean up core.py + cascade
   page fallback constants. Medium impact (removes confusion,
   doesn't change demo behaviour).

3. **v10.324 — Activity generators for other roles** — add
   producers for Branch Operations Supervisor, Branch Manager,
   etc. so they have their OWN actuals (not just team aggregates).
   This makes the "drill to manager → see their KPIs" view richer
   for non-Retail branches.

4. **Demo dry-run + polish** — walk through the cascade page logged
   in as MD, document any UI rough edges, list demo talking points.

Which direction next?
