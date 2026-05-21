# A2Z MIS 360 — Performance Management Framework Review

**Version anchor:** v10.376 (May 2026)
**Purpose:** Deep survey of the BSC + KPI Library + Target Cascade ecosystem — the **primary purpose** of the system. Maps the integration points where the canonical profitability work (v10.368-v10.375) joins the broader Performance Management framework. Written in direct response to Joshua's course-correction: *"the other objective of the entire system is performance management and we have a whole performance framework with BSC and KPI with a target cascade from the MD, I really don't want us to lose the gist of this system."*

**Companion to:** `docs/SYSTEM_STATE_REVIEW_v10.373.md` (overall system mapping). This document zooms into the Performance Management framework specifically.

---

## Part 1 — The Performance Management framework (what exists today)

### Core artifacts (verified counts)

| Artifact | Count | File / Module |
|---|---:|---|
| **KPI definitions** | 185 (109 active) | `data/kpi_library.json::kpis` |
| **Pillars** | 4 main + 2 sub (Process, Risk) | `data/kpi_library.json::pillars` |
| **Roles with KPI assignments** | 227 | `data/kpi_library.json::role_kpis` |
| **Target cascade entries** | 1,051 | `data/target_cascade.json` |
| **Distinct KPIs cascaded** | 21 | derived from target_cascade |
| **Actuals records (latest period)** | 8,167 in 2026-Q2 | `data/bsc_actuals_2026-Q2.json` |
| **MD's KPIs (BSC)** | 12 | role_kpis['Managing Director'] |
| **Branch Manager's KPIs** | 21 | role_kpis['Branch Manager'] |

### The 4 BSC Pillars (with current weights)

Note discrepancy between `pillars` array (40/25/25/10) and `pillar_weights` field (68/14/6/12) — admin has shifted to financial-heavy weighting in production:

| Pillar | Library weight | Current weight | Active KPIs |
|---|---:|---:|---:|
| Financial | 0.40 | **0.68** | 38 |
| Customer Focus | 0.25 | 0.14 | 18 |
| Operational Excellence | 0.25 | 0.06 | 25 |
| People & Learning | 0.10 | 0.12 | 12 |
| Process (sub) | — | — | 13 |
| Risk (sub) | — | — | 3 |

### Engine modules

| Module | LOC | Purpose |
|---|---:|---|
| `utils/bsc_engine.py` | 693 | submit() / get_actual() / get_actuals_for_period() / submit_batch() |
| `utils/bsc_score_computation.py` | 555 | get_target_for_staff() / compute_score() / pillar aggregation |
| `utils/cascade_hierarchy.py` | ~200 | cascade_chain_from_role() / md_direct_reports() / role tree |
| `utils/kpi_aggregation_rules.py` | ~ | Aggregation rules per KPI (sum / avg / weighted) |
| `utils/kpi_ownership.py` | ~ | Which staff own which KPIs |
| `utils/performance_insights.py` | ~ | Insight generation from BSC scores |
| `utils/performance_talent.py` | ~ | Talent management overlay |

### Data flow (today)

```
KPI Library (kpi_library.json::kpis)
  ↓ defines 109 active KPIs
Target Cascade (target_cascade.json)
  ↓ MD sets 21 KPI targets → cascades to 12 direct reports → onwards
BSC Submit (bsc_engine.submit) — multiple source_modules
  ↓ produces per-staff actuals (bsc_actuals_<period>.json)
BSC Score (bsc_score_computation)
  ↓ joins actuals + targets, weights by pillar, aggregates
BSC Data (bsc_data.json — perspectives + scores)
  ↓ consumed by
MD Cockpit BSC Summary tab + pages/1_perform.py (canonical BSC)
```

---

## Part 2 — Where canonical PBT (v10.370) fits

### Discovery: PBT IS a BSC KPI

```python
{
    'id': 'PBT', 'code': 'PBT', 'name': 'PBT',
    'pillar': 'Financial', 'weight': 0.2,
    'unit': 'KES M', 'direction': 'higher',
    'active': True,
    'source': 'management_accounts',  # ← THIS is the drift
    'description': 'Profit Before Tax (KES M) — strategic profitability metric'
}
```

PBT is one of MD's 12 KPIs, with the highest individual weight (0.2 of Financial pillar's 0.68 = ~13.6% of total BSC). It's already wired into:
- Target cascade: `300001|PBT|2026 → 22,000,000,000 → 12 allocations to direct reports`
- BSC actuals submission: any module can submit with `source_module=...`

### The drift

The canonical PBT engine (v10.370 atomic + v10.372 converged) does NOT currently submit to BSC actuals. Its `source` field still says `management_accounts`. So:

- **Canonical PBT exists** (v10.370 G256/G257 with full bank/SBU/branch/customer/staff reconciliation)
- **Cascaded PBT target exists** (v10.371 G258 multi-level schema)
- **BSC actuals exist** (in bsc_actuals_*.json, but populated from somewhere else)
- **The bridge between them does not exist yet**

This is exactly the kind of drift Joshua warned about. Engine excellence in isolation doesn't help if it doesn't feed the Performance Management framework.

### What v10.376 adds

The first concrete bridge: `utils/canonical_pbt_bsc_view.py` exposes a read-only view that:
1. Runs canonical PBT (`compute_pbt_from_cbs`)
2. Reads MD's PBT target from `target_cascade.json::300001|PBT|2026`
3. Reads the cascade allocations (12 direct reports + their cascaded targets)
4. Returns a unified view: `{actual, target, achievement_pct, allocations}`
5. The MD cockpit's BSC Summary tab consumes this view to show PBT with full drill paths

**This is READ-ONLY by design.** A write-side bridge (submit canonical PBT to bsc_actuals) is deferred. We need to first understand all `bsc_engine.submit()` callers to avoid breaking consumers. Write-bridge is v10.377+ scope.

---

## Part 3 — The unification pattern, generalized to Performance Management

The profitability arc (v10.368-v10.372) closed 6 identities for PBT alone:
- Σ SBU = Bank, Σ Branch = Bank, Σ Customer = Bank, Σ Staff = Bank, Σ cascade target = bank target, Engine A = Engine B canonical

**The same pattern applies to every other active KPI** (108 more — 109 active minus PBT). Each KPI needs:

| Element | What it means | Status (PBT vs others) |
|---|---|---|
| **Atomic unit** | The smallest measurement point | PBT: per-customer ✓ / Others: ? |
| **Canonical engine** | Single source of truth | PBT: 4 engines (v10.370) ✓ / Others: scattered or manual |
| **Reconciliation identity** | Σ(atoms) = aggregate | PBT: 6 identities ✓ / Others: ad hoc or none |
| **Target hierarchy** | Multi-level schema | PBT: v10.371 multi-level ✓ / Others: legacy 2-segment |
| **BSC bridge** | Feed canonical to bsc_actuals | PBT: v10.376 read view (write TBD) / Others: not started |
| **Audit gate** | Lock the identity | PBT: G250-G258 / Others: none |

109 active KPIs × ~6 components per KPI = a substantial program. **Phase D in the system roadmap is where this work lives**, by pillar:

| Phase D batch range | KPI pillar | Active KPIs |
|---|---|---:|
| v10.40X | Financial (excluding PBT — done) | 37 |
| v10.41X | Customer Focus | 18 |
| v10.42X | Operational Excellence | 25 |
| v10.43X | People & Learning | 12 |
| v10.44X | Process (sub) | 13 |
| v10.44X | Risk (sub) | 3 |

PBT was the **prototype**. Phase D applies the pattern to the remaining 108 KPIs.

---

## Part 4 — Existing performance-management drift to fix

A 360° review surfaces these alignment gaps:

### 4.1 KPI-ID drift

MD's 12 KPIs in `role_kpis['Managing Director']` include `DEP_GROWTH`, `LOAN_GROWTH`, `FEES_COMM`, `CIR`, `NIM`, `ROE`, `NEW_CUST`, `DIGITAL_ACT`, `NPS` — **none of these have definitions in `kpi_library.json::kpis`**. They're referenced but not defined. The cascade and BSC may use different KPI IDs for the same metric (e.g. "PBT" vs "K001" vs "FINANCIAL_PBT").

**Fix scope**: a KPI ID canonicalisation batch (likely v10.378 or thereabouts) — every reference uses the same ID; legacy IDs migrate via aliases.

### 4.2 Pillar weight drift

`pillars` array shows 40/25/25/10; `pillar_weights` field shows 68/14/6/12. Both are loaded by different consumers. Different consumers may produce different BSC totals.

**Fix scope**: single weight source per pillar with admin governance. Lock via audit gate.

### 4.3 Source-module drift

BSC actuals records have `source_module` field (e.g. `'verification_test'` in the 2026-Q2 sample). Many actuals are seeded by activity generators, not by real engines. The PBT actual today probably comes from `mgmt_accounts.py` or similar — not from the canonical CBS-based engine.

**Fix scope**: each KPI has a single authoritative source_module; canonical engines submit; other source_modules deprecated.

### 4.4 Target cascade KPI mismatch

Target cascade has 21 distinct KPIs but the KPI Library has 109 active. Only ~19% of active KPIs have cascade targets. The remaining 80% of KPIs are scored against fixed thresholds, not cascaded targets.

**Fix scope**: identify which KPIs need cascade vs which should stay fixed-threshold. Some KPIs (NPS, audit score) don't naturally cascade — they're absolute thresholds. Others (deposit growth, fee income) genuinely should cascade.

### 4.5 Role-KPI map vs role taxonomy

`role_kpis` has 227 roles. v10.374 role taxonomy classified 126 distinct roles from users.json + hr.json. The 101 extra roles in `role_kpis` likely include legacy variants, role aliases, or aspirational roles not yet staffed.

**Fix scope**: alignment audit — every `role_kpis` key should map to a tier in the v10.374 profitability axis OR be flagged as deprecated. v10.374's `_aligns_with` field already lists this as a downstream alignment target.

---

## Part 5 — The MD's Daily Question, answered properly

> **MD's question:** *"Is the bank on track to achieve its strategic goals?"*

The system's job is to answer this in real-time with mathematical defensibility. Today's answer paths:

| Path | What it shows | Authority |
|---|---|---|
| MD Cockpit Tab 2 (BSC Summary) | 4 pillar scores | Today reads `bsc_data.json` |
| MD Cockpit Tab 6 (Financial Snapshot) | Management accounts highlights | Today reads MA files |
| pages/1_perform.py | Full per-staff scorecard | Canonical BSC view |
| pages/12_cascade.py | Target cascade tree | MD's allocation to 12 direct reports |
| pages/120_staff_pbt.py (v10.375 NEW) | Per-staff PBT drill | Canonical PBT (v10.370) |

**The gap**: these views don't agree on PBT because they read from different sources. The MD seeing 22B target on cascade page and seeing 18B "actual" on BSC summary doesn't know which actual is authoritative.

**The fix v10.376 ships**: the MD cockpit BSC Summary tab now shows canonical PBT alongside cascaded target, with drill links to SBU (v10.368), Branch (v10.369), and Staff (v10.370 / v10.375 page). One number; full lineage.

---

## Part 6 — Refined roadmap (with PM framework as primary)

Joshua's body-system framing made explicit: PM is the central nervous system of the bank. PBT was one organ. Phase B+C+D extend the unification across the body.

### Phase A — Surface canonical PBT in PM framework (current)

| Batch | Concern | Status |
|---|---|---|
| ~~v10.373~~ | System State Review | CLOSED |
| ~~v10.374~~ | Role Taxonomy | CLOSED |
| ~~v10.375~~ | Staff PBT Page | CLOSED |
| **v10.376 (this)** | PM Framework Review + canonical PBT → MD BSC tab | **Closing** |

### Phase B — Close remaining parallel profitability engines + customer master

| Batch | Concern |
|---|---|
| v10.377 | Customer master merge (per Joshua approval "merge into 1") |
| v10.378 | KPI ID canonicalisation (fix kpi_library / role_kpis / cascade ID drift) |
| v10.379 | Refactor `customer_profitability.py` to canonical |
| v10.380 | Refactor `rm_profitability.py` to canonical |
| v10.381 | Refactor remaining `sbu_pnl_rollup.rollup_by_*` entry points |

### Phase C — Live action interfaces (grouped, per Joshua)

| Batch | Group |
|---|---|
| v10.382 | Branch field staff actions (CSO, BOS, RM PB, RM BB, DSO) |
| v10.383 | Branch management actions (Branch Ops Mgr, Branch Credit Mgr, Branch Mgr) |
| v10.384 | Head Office sales actions (HO Corporate/SME/Sector RMs, Proposition owners) |
| v10.385 | Regional / Division leadership (Area Mgrs, Heads, Chiefs) |
| v10.386 | Head Office support (Credit, Treasury, Risk, Compliance, AML, Audit, Finance, IT, HR) |
| v10.387 | C-suite (CFO, CRO, MD) |

### Phase D — KPI unification pattern across all 108 remaining KPIs

| Batch range | Pillar | KPIs to canonicalise |
|---|---|---:|
| v10.40X-41X | Financial (excluding PBT) | 37 |
| v10.41X-42X | Customer Focus | 18 |
| v10.42X-43X | Operational Excellence | 25 |
| v10.43X-44X | People & Learning | 12 |
| v10.44X | Process | 13 |
| v10.44X | Risk | 3 |

### Phase E — Executive UI (React frontend per Standard #9)

v10.45X+

---

## Part 7 — What v10.376 actually delivers

**Read this section if nothing else.** This is the concrete scope of THIS batch:

1. **This review document** — locks the PM framework understanding so future batches don't drift
2. **`utils/canonical_pbt_bsc_view.py`** — read-only bridge with `get_md_pbt_summary(cbs_dir, period)` returning canonical PBT + cascade target + achievement % + 12-way allocation drill
3. **MD cockpit BSC Summary tab enhancement** — adds a "Canonical PBT" card that consumes the bridge view, with deep-link to `pages/120_staff_pbt.py` (v10.375)
4. **G262 audit gate** — locks the review document + bridge module + MD cockpit integration
5. **Tests** — 10-12 covering the bridge + integration + no-regression to prior 7 unification identities

**This batch does NOT**:
- Write canonical PBT into bsc_actuals (write-bridge deferred to v10.377+)
- Fix KPI-ID drift (deferred to v10.378)
- Refactor pillar weights (separate batch)
- Touch the 108 other active KPIs (Phase D scope)
- Touch role_kpis (deferred to v10.378 alignment work)
- Modify the BSC engine, cascade engine, or scorecard computation

Single concern: **surface canonical PBT in the MD's BSC view, read-only**. Build pattern that Phase D will follow for every other KPI.

---

## Part 8 — Decisions awaiting Joshua (after v10.376 ships)

1. **Pillar weights** — keep current 68/14/6/12 (financial-heavy) or revert to library 40/25/25/10? This drives MD's BSC composite score directly.
2. **KPI ID canonicalisation** — which ID system wins? The text-based "PBT" / "NIM" / "ROE" or numeric "K001" / "K002"? Today both coexist.
3. **Write-side bridge** — when canonical engines feed `bsc_engine.submit()`, do they replace existing source_modules or coexist? Today's bsc_actuals has many source_modules; adding a new one is safe; deprecating an old one is risky.
4. **Cascade-vs-fixed-threshold** — for 80% of active KPIs without cascade, do we want to add cascade (more management overhead) or formalise them as fixed thresholds (less flexibility)?

---

## Part 9 — Honest acknowledgement of drift

I (Claude) went deep on PBT unification (v10.368-v10.372) without fully integrating with the PM framework. The cumulative result: engine excellence in isolation. Joshua's intervention is what prevented this from accumulating further.

The pattern is now corrected: **every future canonical engine must include a BSC bridge as part of its ship scope**. The unification work is incomplete without the integration into Performance Management, because Performance Management is the system's primary purpose.

v10.376's review document + bridge + MD cockpit integration is the pattern. Phase D batches will follow it for every other KPI.
