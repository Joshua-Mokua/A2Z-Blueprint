# Changelog — v10.334 Specialized Segments / Propositions arm

**Date:** 2026-05-12
**Phase:** 4 (nineteenth arc — bringing every department to life)
**Audit:** 223/223 gates PASS = 100.0%
**Tests:** 660/660 passing across 39 integration suites (12 new for v10.334)
**G162 Baseline:** 4022 — 28 consecutive zero-drift batches

---

## Your design ask (verbatim)

> "ensure every department and all staff are fully operating and every
> module is interconnected as supposed. We had defined SBU and how
> the customers are segmented and the various propositions that have
> heads and staff, lets now bring that arm to live now, then move to
> products"

## The state I started from

Of 1,439 active staff in the universe, only 805 were scoring in Q2.
The gap of 634 broke down across departments — most concentrated in
Retail Banking branch staff (CSOs, Branch RMs, Personal/Business
Bankers) but those are leaves of the BM cascade and roll up through
the BM scorecard.

**The real gap you flagged was the Propositions arm.** 8 propositions
defined across 7,737 segment-tagged customers, but only 5 had scoring
heads in Q2:

| Code | Proposition | Customers | Head Status (pre-v10.334) |
|------|-------------|-----------|---------------------------|
| WB | Women Banking | 2,737 | **— not scoring** |
| DIA | Diaspora | 780 | **— not scoring** |
| AGR | Agribusiness | 763 | **— not scoring** |
| SME | SME/MSME | 1,720 | 3.00 (Pipeline bridge) |
| GOV | Public Sector | 245 | 1.00 (Pipeline bridge) |
| TF | Trade Finance | 241 | 1.83 (Pipeline bridge) |
| BNC | Bancassurance | 251 | 2.55 (Pipeline bridge) |
| DFS | Digital FS | 1,000 | 3.71 (Support gen) |

WB had a head (300013) but no team. DIA + AGR shared a head (300014
Sr Mgr Diaspora) plus 5 staff — none scoring.

## What v10.334 shipped

### `utils/proposition_activity_generator.py`

Fifth Phase 4 producer. Mirrors v10.317 Teller / v10.327 Credit /
v10.328 Support / v10.329 BM patterns. Same design principles:
deterministic, idempotent, direction-aware, scale-aware, audit-logged.

**Scope:** 8 staff in the Specialized Segments arm:
- 300013 Head Of Women Banking (WB)
- 300014 Senior Manager Diaspora Banking (DIA + AGR — shared head)
- 300015, 300016 Relationship Manager - Diaspora (DIA)
- 300038, 300039 Relationship Manager - Agribusiness (AGR)
- 300205, 300206 Senior Relationship Officer - Diaspora Banking (DIA)

**Output:** 63 KPIs per quarter × 4 quarters = **252 BSC actuals**.

### `data/proposition_activity_config.json`

Defines KPI bases for each of the 4 role types. Each KPI has:
- `base`: scaled to segment customer count
- `unit`: CCY_M (currency-agnostic), %, count, score_5, score_100
- `direction`: higher or lower

Currency-agnostic sentinel `CCY_M` instead of `KES M` — same fix as
v10.331 (avoid G162 tenant-identity drift). The runtime scales by
1,000,000 regardless of which currency is configured in
`org_config.json`.

### `data/kpi_library.json` — 4 roles migrated

Same pattern as v10.324 (Commercial roles) + v10.328 (Support roles).
Moved 4 specialized segment roles from K-coded role_kpis to canonical
KPI names matching what the generator submits:

| Role | Before | After |
|------|--------|-------|
| Head Of Women Banking | K001, K002, K006, K007, K009, K016, K019, K020 | PBT, Total NFI, Retail & MSME Deposit Growth, Top 100 Customers Deposit, Number of Business Borrowers, CX Score, COMPLIANCE_SCORE, Staff Productivity |
| Senior Manager Diaspora Banking | K001, K002, K003, K005, K006, K007, K016, K019, K020 | + Commercial Deposit Growth (9 canonical) |
| Relationship Manager - Diaspora | K001, K002, K003, K006, K007, K016, K019, K020 | Disbursements MSME Loans, Retail & MSME Deposit Growth, Total NFI, Number of Business Borrowers, NPL_RATIO, Audit Score, CX Score, COMPLIANCE_SCORE |
| Senior Relationship Officer - Diaspora Banking | K001, K002, K003, K006, K016, K019, K020 | Disbursements MSME Loans, Retail & MSME Deposit Growth, Total NFI, Number of Business Borrowers, Audit Score, CX Score, Staff Productivity |

Tagged `_v10334_role_kpi_canonical_migration` with full rollback
metadata (previous K-codes preserved).

## Verified outcome — all 8 propositions now scoring

### 2026-Q2 head scores

| Code | Head | Q2 Score |
|------|------|---------|
| **WB** | Head Of Women Banking | **2.83** (was —) |
| **DIA** | Senior Manager Diaspora Banking | **2.90** (was —) |
| **AGR** | (shared with DIA) | **2.90** (was —) |
| SME | Head of MSME | 3.00 |
| GOV | Head GIB | 1.00 |
| TF | Head Corporates & TF | 1.83 |
| BNC | GM Bancassurance | 2.55 |
| DFS | Head of DFS | 3.71 |

### Specialized Segments staff Q2 (all scoring for the first time)

| Code | Role | Score |
|------|------|-------|
| 300013 | Head Of Women Banking | 2.83 |
| 300014 | Sr Mgr Diaspora Banking | 2.90 |
| 300015 | RM - Diaspora | 3.50 |
| 300016 | RM - Diaspora | 3.21 |
| 300038 | RM - Agribusiness | 2.53 |
| 300039 | RM - Agribusiness | 2.78 |
| 300205 | Sr RO - Diaspora Banking | 2.50 |
| 300206 | Sr RO - Diaspora Banking | 3.50 |

### 4-quarter trend

| Prop | Q3'25 | Q4'25 | Q1'26 | Q2'26 |
|------|-------|-------|-------|-------|
| WB | 2.83 | 2.67 | 3.00 | 2.83 |
| DIA | 2.88 | 2.81 | 2.90 | 2.90 |
| AGR | (shared) | (shared) | (shared) | (shared) |
| DFS | 3.66 | 3.69 | 3.67 | 3.71 |

WB + DIA producing 4-quarter trends now. SME/GOV/TF/BNC trend will
build over time as the pipeline bridge accumulates history.

## New audit gate G223 — specialized_segments_integration

6 invariants:
1. `utils/proposition_activity_generator.py` exists with canonical surface
2. `data/proposition_activity_config.json` defines WB + DIA + AGR
3. Generator finds ≥7 active staff in scope
4. BSC actuals 2026-Q2 has ≥50 records `source_module='proposition_activity_generator'`
5. All 8 proposition heads have computed scores in 2026-Q2
6. WB Head + Sr Mgr Diaspora score in all 4 quarters

## Files changed

| File | Change |
|------|--------|
| `utils/proposition_activity_generator.py` | NEW — 245 lines |
| `data/proposition_activity_config.json` | NEW — 3 propositions, 4 role KPI configs |
| `data/kpi_library.json` | +4 role_kpis migrated to canonical, provenance tagged |
| `data/bsc_actuals_2025-Q3.json` | +63 specialized segments actuals |
| `data/bsc_actuals_2025-Q4.json` | +63 |
| `data/bsc_actuals_2026-Q1.json` | +63 |
| `data/bsc_actuals_2026-Q2.json` | +63 |
| `data/cascade_scores_*.json` | All 4 quarters re-precomputed with full rollups (v10.333 perf) |
| `scripts/audit.py` | NEW G223 gate function + registration |
| `tests/integration/test_v10334_specialized_segments.py` | NEW — 12 tests across 5 sections |

## Platform state

| Metric | v10.333 → v10.334 |
|--------|-------------------|
| Audit gates | 222 → **223** |
| Integration test suites | 38 → **39** |
| Tests passing | 648 → **660** |
| Producer batches | 5 → **6** (Teller, Pipeline, Credit, Support, BM, Propositions) |
| Specialized segments staff scoring | 0 → **8** |
| Propositions with scoring heads | 5 of 8 → **8 of 8** |
| Total Phase-4 producer staff | 548 → **556** |
| G162 baseline | 4022 (28 consecutive zero-drift batches) |

## Real findings during this batch

1. **The infrastructure was already there.** All 8 propositions had
   role_kpis defined, segments had customer tags (7,737 customers
   linked to propositions), Heads existed in the org structure. What
   was missing: BSC actuals being produced for them.

2. **The K-code → canonical migration was the third pattern.** Same
   issue as v10.324 (Commercial) and v10.328 (Support): old role_kpis
   used K-codes (K001 = "Loans Disbursed KES M") but the generator
   submits canonical names (PBT, Total NFI, etc.). The K-codes are
   still valid KPI definitions but they don't get fed by the
   producer pipeline. Migration is the right fix; preserves rollback
   via `_v10334_role_kpi_canonical_migration` provenance.

3. **The "no team" case (WB) works.** Head Of Women Banking has zero
   direct reports — WB is cross-functional, served by branch RMs who
   happen to bank women. The Head still gets a scorecard because the
   segment owner is accountable for segment growth. Their score
   reflects WB segment-level performance.

4. **AGR sharing a head with DIA is normal.** Sr Mgr Diaspora 300014
   covers both Diaspora and Agribusiness customers in this bank. One
   staff_code, two propositions tagged separately in customer base.
   Both segments roll up through the same scorecard. Realistic for
   smaller specialized segments.

5. **Two architecture compliance issues fixed pre-ship.** Initial
   draft had `read_text()` direct I/O (G2) and `KES M` literal in
   code+config (G162). Both caught by audit on first run; fixed
   before ship. Same patterns as v10.331 (db.load_json) and same
   currency sentinel approach.

6. **G162 holds at 4022.** 28 consecutive zero-drift batches now.

## What's NOT in v10.334

1. **No new Heads invented.** AGR didn't have a dedicated Head; I
   could have promoted one of the RMs but the realistic banking
   structure is Sr Mgr Diaspora covering both. Logged as observed,
   not a problem.

2. **No new propositions added.** The 8 in the config match exactly
   what's already in `proposition_config.json` from earlier work.

3. **The cascade dipped MD slightly (3.37 → 3.34) and Retail (3.36
   → 3.11).** Honest result: WB + Diaspora coming online with below-
   network-average scores pulls the recursive mean down. This is the
   cascade telling the truth about segment performance.

4. **SBU view page not built.** The user mentioned "SBU and how the
   customers are segmented" — `pages/9_sbu.py` and the engines exist;
   they consume the new actuals automatically. A dedicated cascade
   page showing per-proposition performance is a v10.335 candidate.

## Backlog status

| ID | Status |
|----|--------|
| B-023 | Open — Credit Monitoring under Analysis vs Collections |
| B-025 | Open — Hierarchy layer order hardcoded |
| B-026 | Open — Branch-ranking thresholds hardcoded |
| B-027 | NEW — Other "orphan" staff (Marketing, Treasury, Trade Finance specialists, Internal Auditors below 300150 etc) still ~50 staff non-scoring in their depts |
| B-009 - B-021 except closed | Unchanged |

## Suggested next batches

The Propositions arm is alive. Next:

1. **v10.335 — Products arm** (your stated next step) — wire products
   to revenue, cross-sell, lifecycle into the BSC cascade
2. **v10.335 — Remaining department coverage** — Treasury (7 staff
   non-scoring), Trade Finance specialists (7 staff), Marketing (4),
   plus the 50 misc orphans across smaller depts
3. **v10.335 — SBU drill-down page** — dedicated per-proposition view
   on the cascade page, surfacing customer counts + segment
   performance

Which direction?
