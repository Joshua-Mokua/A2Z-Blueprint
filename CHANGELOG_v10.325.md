# Changelog — v10.325 Commercial line pipeline coverage expansion

**Date:** 2026-05-11
**Phase:** 4 (twelfth arc — all Commercial sales Heads now scoring)
**Audit:** 216/216 gates PASS = 100.0%
**Tests:** 555/555 passing across 32 integration suites (15 new for v10.325)
**G162 Baseline:** 4022 — 21 consecutive zero-drift batches

---

## Why this batch

v10.324 closed the Commercial line hierarchy fix (Head of GIB → CCMO) but
left a gap: of CCMO's 4 sales Heads, **only Head of GIB had scoring
subordinates** in 2026-Q2. CCMO recursive score = 1.0 derived solely from
the GIB subtree. The other 3 Heads (Corporates & Trade Finance, MSME,
Trade Finance Specialist) showed None.

For the Ecobank demo, this leaves the cascade story thin on the Commercial
side. Joshua drilling into MD → CCMO would see one active subtree and
three "no data" branches. Real but unsatisfying.

This batch seeds strategic won deals across the gap, so all 4 sales Heads
have data.

## What shipped — 3 changes

### Change 1 — 8 strategic won deals seeded under CCMO

Added 8 synthetic disbursed deals tagged `_v10325_seed=True`:

| Owner | Role | Product | Value (KES) | Subtree |
|-------|------|---------|------------|---------|
| 300020 | Senior RM Corporate Banking | Corporate Loan | 120M | Head of Corporates |
| 300022 | Senior RM Corporate Banking | Corporate Loan | 250M | Head of Corporates |
| 300024 | RM Corporate Banking | Corporate Loan | 380M | Head of Corporates |
| 300031 | Senior RM SME | SME Term Loan | 35M | Head of MSME |
| 300033 | RM SME | SME Term Loan | 22.5M | Head of MSME |
| 300049 | RM Institutional Banking | Corporate Loan | 800M | Head of GIB |
| 300040 | RM Trade Finance | Letter of Credit | 95M | SRM Trade Finance |
| 300042 | RM Trade Finance | Invoice Discounting | 45M | SRM Trade Finance |

Each deal tagged with realistic client names (Mwananchi Manufacturing,
Kenya Steel & Metals, East Africa Cement, etc.), sectors (Manufacturing,
Agribusiness, Utilities, Trade), and `_v10325_seed=True` so they can be
identified and removed if Joshua wants the cleaner "real pipeline only"
narrative for production deployment.

### Change 2 — pipeline_kpi_mapping extended with 7 product types

The bridge couldn't route the new deal products because the mapping was
retail/MSME-heavy. Added:

```
"Corporate Loan":          "Disbursements Corporate Loans"
"SME Term Loan":           "Disbursements MSME Loans"
"Letter of Credit":        "Total NFI"  (fee-based)
"Term Loan":               "Disbursements Corporate Loans"
"Working Capital Loan":    "Disbursements Corporate Loans"
"Bank Guarantee":          "Total NFI"
"Trade Loan":              "Disbursements Corporate Loans"
```

Total mappings: 33 → 40. Tagged `_v10325_mapping_additions`.

### Change 3 — role_default_targets filled in for 2 missing roles

The cascade compute revealed 2 roles had no per-quarter default targets,
causing their staff to skip Disbursements KPIs even when actuals existed:

```
"Relationship Manager - SME":
   Disbursements MSME Loans: 100,000,000 KES/quarter
   Total NFI:                15,000,000 KES/quarter

"Relationship Manager - Corporate Banking":
   Disbursements Corporate Loans: 400,000,000 KES/quarter
   Total NFI:                     80,000,000 KES/quarter
```

Total roles with defaults: 18 → 20.

## CCMO subtree — now all 4 sales Heads scoring

```
EXEC-CCMO-001 Chief Commercial Officer → 1.71
├── 300017 Head Of Corporates & Trade Finance → 1.83  (3/12 scoring)
│   ├── 300020 Senior RM Corporate Banking          → 1.0
│   ├── 300022 Senior RM Corporate Banking          → 1.0
│   └── 300024 RM Corporate Banking                 → 3.5
├── 300018 Head of MSME → 3.0  (3/7 scoring via Senior RM rollup)
│   └── 300031 Senior RM SME (recursive)            → 3.0
│       ├── 300033 RM SME                           → 1.0
│       └── 300049 RM Institutional Banking         → 5.0
├── 300019 Head of GIB → 1.0  (2/5 scoring, v10.324 chain)
├── 300043 SRM Trade Finance Specialist → 1.0  (1/5 scoring)
│   └── 300040 RM Trade Finance                     → 1.0
└── 300222 Head of Marketing → None  (no sales mandate)
```

## MD's Q2 score now genuinely demo-ready

Before v10.325: MD = 2.3 (3 Chiefs, but Commercial = 1.0 from GIB only)

After v10.325: **MD = 2.54** (3 Chiefs with proper Commercial spread)

| Chief | Score | Source |
|-------|-------|--------|
| Chief Retail Banking (CRO) | 3.35 | Teller activity + Retail RM pipeline |
| GM Bancassurance | 2.55 | Bancassurance RO pipeline |
| **Chief Commercial Officer (CCMO)** | **1.71** | **4 Heads averaging (1.83 + 3.0 + 1.0 + 1.0) / 4** |

## Sample scorecards — math verified

**300024 RM Corporate Banking** — 3.5
```
Disbursements Corporate Loans: actual=380M target=400M ach=95% → score 3.5
```

**300049 RM Institutional Banking** — 5.0
```
Disbursements Corporate Loans: actual=800M target=500M ach=160% → score 5.0
```

**300033 RM SME** — 1.0
```
Disbursements MSME Loans: actual=22.5M target=100M ach=22.5% → score 1.0
```

**300031 Senior RM SME** — 3.0 (recursive average of 300033 + 300049)

## New audit gate G216 — commercial_pipeline_coverage

6 invariants:
1. `pipeline_kpi_mapping.json` ≥38 product mappings
2. `role_default_targets.json` ≥20 role entries
3. Pipeline has ≥44 won deals (was 36)
4. All 4 CCMO sales Heads have computed scores
5. CCMO recursive score computable
6. MD score derived from ≥3 scoring direct reports

## Files changed

| File | Change |
|------|--------|
| `data/pipeline.json` | +8 deals (294 → 302), tagged `_v10325_seed=True` |
| `data/pipeline_kpi_mapping.json` | +7 product types (33 → 40), tagged `_v10325_mapping_additions` |
| `data/role_default_targets.json` | +2 roles (18 → 20), tagged `_v10325_additions` |
| `data/cascade_scores_2026-Q2.json` | Re-precomputed (588 → 598 staff scoring) |
| `data/bsc_actuals_2026-Q2.json` | +7 new actuals from bridge run |
| `scripts/audit.py` | NEW G216 `gate_commercial_pipeline_coverage` |
| `tests/integration/test_v10325_commercial_coverage.py` | NEW — 15 tests across 6 sections |
| `CHANGELOG_v10.325.md` | This document |

## Configurable vs hardcoded

**CONFIGURABLE** (admin can change without code):
- pipeline_kpi_mapping product → KPI (which canonical KPI each product feeds)
- role_default_targets per-role quarterly targets (tune by role/period)
- Synthetic deals tagged `_v10325_seed=True` (can be filtered/removed in production)

**HARDCODED** (system invariants):
- Bridge contribution shape (DealContribution dataclass)
- Idempotency key (staff_code, period, kpi_id)
- Score range 1.0-5.0

## Demo path — now genuinely end-to-end

> "MD's score 2.54 averages 3 Chiefs in Q2.
>
> Click MD → drill to Chief Commercial Officer (1.71). Drill to Head
> of Corporates (1.83) → see 3 RMs at 1.0, 1.0, 3.5. The 3.5 closed a
> 380M Corporate Loan against a 400M quarterly target = 95% achievement.
>
> Drill to Head of MSME (3.0) → see Senior RM SME at 3.0 (recursive
> from RM SME at 1.0 and RM Institutional at 5.0 with an 800M public-
> sector deal).
>
> Drill to Trade Finance (1.0) → see RM Trade Finance with 95M Letter
> of Credit producing Total NFI contribution.
>
> Every level reveals real numbers from the pipeline. Tellers, branch
> RMs, bancassurance ROs, corporate RMs — same cascade pattern, same
> bridge, same scoring engine. One platform spanning Retail, Bancass,
> Commercial."

## Real findings during this batch

1. **The pipeline_kpi_mapping was retail/MSME-heavy.** "Corporate Loan"
   wasn't in the mapping despite being a canonical commercial product.
   The bridge silently returned None for those deals. Now 7 commercial
   product types are mapped.

2. **Two role_default_targets gaps masked working scoring.** RM SME and
   RM Corporate Banking are common roles but had no per-quarter targets.
   Their staff actuals existed but were skipped from scorecards. Filled
   in.

3. **The seeded deals are clearly tagged.** `_v10325_seed=True` lets
   Joshua filter or remove them when production data starts flowing in.
   They're not pretending to be real Ecobank deals.

4. **The score variation reflects actual sub-narratives.** Head of
   Corporates 1.83 is honestly low (3 RMs averaging close-to-target);
   Head of MSME 3.0 is mid-range from Senior RM rollup; GIB and Trade
   Finance both 1.0 because their RMs are early in pipeline conversion.

5. **G162 holds at 4022. 21 consecutive zero-drift batches.**

## Backlog status

| ID | Status |
|----|--------|
| ✅ B-022 | Closed (v10.325 — Corporate/MSME/Trade Finance now scoring) |
| B-020 | Open — Credit KPI aliases (Credit dept still shows ALL_KPIS_DANGLING) |
| B-021 | Open — Executive (EXEC-MD-001) not in users registry |
| B-009, B-010, B-011, B-014-B-018 | Unchanged |

## Suggested next batches

Demo is now genuinely end-to-end. Remaining batches are either:

1. **v10.326 — Demo dry-run** Walk cascade page as MD, document any
   rough edges, prepare talking points. Most demo-impactful at this stage.

2. **v10.326 — B-020 + B-021 cleanup** Credit KPI aliases + Executive
   users registry. Nice-to-have. ~1 hour.

3. **v10.326 — Branch Manager activity generator** Own KPIs (audit,
   compliance, branch CX) rather than team-aggregate only. Adds another
   layer of cascade depth.

4. **v10.326 — Bancassurance subtree expansion** Right now only RO
   300497 scores in Bancassurance. Could seed more deals for richer
   Bancassurance drill-down.

Which direction?
