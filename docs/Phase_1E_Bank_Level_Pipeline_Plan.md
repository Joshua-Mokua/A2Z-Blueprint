# Phase 1E — Bank-Level Pipeline Charter

**Sprint span:** v10.269 (this batch) → estimated v10.275 closure
**Author:** Joshua Mokua / A2Z MIS 360
**Status:** PLANNING — implementation begins next batch (v10.270)
**Audit at charter:** 163/163 PASS · G143: 99/131 = 75.6% (informational-pass; STRICT-READY high)
**Target at closure:** 163+/163+ PASS · G143: 131/131 = 100% (strict mode candidate) · G144 NEW (bank-level coverage ratchet)

---

## Why this charter exists

Phase 1D Integration Layer (v10.108–v10.125) closed the per-staff aggregation pathway at 99/131 = 75.6% of the KPI library. The 32 KPIs holding G143 below 100% are not bank failures — they are correctly-deferred bank-level aggregates that the per-staff engine cannot answer because they have no staff dimension. The bank's CAR ratio doesn't belong to a person; it's a property of the whole balance sheet.

The Phase 1D retro proposed a separate bank-level pipeline as Phase 1E Category A and estimated 5–8 batches. This charter scopes the work, locks the design choices before code is written, and establishes the audit-locked acceptance criteria.

This document supersedes section "Decision: defer Category A" of `docs/Phase_1D_Integration_Layer_Retro.md` for go-forward planning.

---

## Programme context

A2Z MIS 360 is a 360-degree Management Intelligence Platform for Ecobank Kenya, currently competing against three other vendors. The platform consumes core banking data from FLEXCUBE — it does not replace it. Phase 1D wired per-staff KPIs (loans, recoveries, complaints — anything answerable as "who did what"). Phase 1E wires the remaining bank-level KPIs (CAR, LCR, NSFR, NIM, ROA, NPL ratio — anything answerable as "what's the bank's number right now").

Both pipelines feed the same BSC engine. Both must reach 100% for G143 strict-flip to be safe.

---

## Scope reconnaissance

A live survey of `data/aggregation_rules.json` against `data/kpi_library.json` (executed at charter time, audit 163/163 PASS) returned:

```
Total active KPIs:                     152
Phase 1D rules cover:                  100 (per-staff, all 8 patterns)
Bank-level candidates (CBS autofit):    37
Operational unwired (still per-staff):  15
Total to wire in Phase 1E:              37 (the 32 from retro + 5 added since)
```

The 37 candidates span 11 source files. Not all are in `cbs_data/`; several are top-level snapshot files. The bank-level pipeline must handle both layouts.

### Sources by file (from the live survey)

| Source file | KPIs targeting it | Shape |
|---|---|---|
| `cbs_loans` (cbs_data/) | 6 (Disbursements Corp/MSME/Retail, Loan Book Growth, Business Borrowers, PAR, K004) | list-of-records |
| `cbs_deposits` (cbs_data/) | 4 (CASA Ratio, Commercial/Retail-MSME Deposit Growth, K002) | list-of-records |
| `cbs_fees` (cbs_data/) | 1 (K003) | list-of-records |
| `cbs_accounts` (cbs_data/) | 3 (Account Dormancy, K006, K009) | list-of-records |
| `mgmt_accounts.json` | 3 (K005, K021, PBT) | nested-snapshot (income_statement / balance_sheet / key_ratios) |
| `capital_adequacy.json` | 4 (K080–K083 — CET1/Tier1/CAR/RWA) | flat-snapshot (as_at + scalar fields) |
| `liquidity_metrics.json` | (used by K082/K083 alongside capital) | flat-snapshot |
| `alm_liquidity.json` | 4 (K094–K097 — IRRBB/gap analysis/ALCO) | dict-of-arrays |
| `cybersecurity.json` | 1 (K026) | flat-snapshot |
| `digital_channels.json` | 3 (Channel Dormancy, K012, K024) | nested-snapshot |
| `contact_centre.json` | 2 (K031, K032) | nested-snapshot |
| `esg_climate.json` | 3 (K106–K108) | mixed (esg_score nested + green_loans list) |

### Three structural shapes the engine must handle

**A. Flat-snapshot.** Single-row JSON with a date stamp and scalar fields. Read by direct field access. Examples: `capital_adequacy.tier_1_capital`, `cybersecurity.patch_compliance_pct`.

**B. Nested-snapshot.** Single-row JSON with a date stamp and nested dicts. Read by dotted-path traversal. Examples: `mgmt_accounts.key_ratios.nim_pct`, `digital_channels.mobile_app.mau`.

**C. List-of-records.** JSON list where each row is a period-stamped observation. Read by filtering on period, then aggregating. Examples: `alm_liquidity.gap_analysis` (540 records of per-bucket per-date gaps), `esg_climate.green_loans` (40 records).

The Phase 1D engine assumed shape C with a staff dimension. Phase 1E generalises to A + B + C without requiring a staff dimension.

---

## Architecture — the bank-level pipeline

```
  ┌──────────────────────────────┐
  │ data/cbs_loans.json          │── list-of-records ──┐
  │ data/cbs_deposits.json       │── list-of-records ──┤
  │ data/mgmt_accounts.json      │── nested-snapshot ──┤
  │ data/capital_adequacy.json   │── flat-snapshot ────┼──→  utils/bank_aggregator.py
  │ data/liquidity_metrics.json  │── flat-snapshot ────┤      (single-row reducer)
  │ data/alm_liquidity.json      │── dict-of-arrays ───┤
  │ data/cybersecurity.json      │── flat-snapshot ────┤
  │ data/digital_channels.json   │── nested-snapshot ──┤
  │ data/contact_centre.json     │── nested-snapshot ──┤
  │ data/esg_climate.json        │── mixed ────────────┘
  └──────────────────────────────┘
                   │
                   ▼ run once per period
  ┌────────────────────────────────────────────┐
  │  {kpi_id: bank_aggregate_value}            │
  │  (one row per period — no staff dimension) │
  └────────────────────────────────────────────┘
                   │
                   ▼
  ┌──────────────────────────────────┐
  │  /api/integration/bank_level     │
  │  GET ?period=YYYY-MM             │
  │  JWT-protected; role-gated       │
  └──────────────────────────────────┘
                   │
                   ▼
  ┌──────────────────────────────┐
  │  BSC engine bank-level       │
  │  scorecard (one column per   │
  │  pillar, no staff_code col)  │
  └──────────────────────────────┘
```

### New module: `utils/bank_aggregator.py`

Engine module. Single entry point: `compute_bank_level(rule, period) → {value, meta}`. Plus a registry of aggregator functions and a public `compute_all_bank_level(period) → {kpi_id: result}` helper that loops over `data/bank_aggregation_rules.json`.

### New rules file: `data/bank_aggregation_rules.json`

Companion to `data/aggregation_rules.json`. Bank-level rule shape **deliberately differs** from per-staff:

```json
{
  "kpi_id": "K080",
  "active": true,
  "source_file": "capital_adequacy.json",
  "shape": "flat_snapshot",
  "aggregator": "SNAPSHOT_FIELD",
  "field": "tier_1_capital",
  "period_field": "as_at",
  "decimals": 0,
  "_origin": "v10.270 / Phase 1E"
}
```

Versus a per-staff rule:

```json
{
  "kpi_id": "K011",
  "active": true,
  "source_table": "loan_applications",
  "pattern": "TAT_DAYS",
  "start_field": "submission_date",
  "end_field": "disbursement_date",
  "predicate": {...},
  "period_field": "submission_date",
  "decimals": 1
}
```

**No `pattern` (uses `aggregator` instead). No `predicate` (bank-level rules do not filter by who; they filter by period). No staff field at all.** This is intentional — a Phase 1D rule cannot accidentally be loaded as a Phase 1E rule and vice versa.

### Aggregator catalog (the bank-level equivalent of the 8 universal patterns)

| Aggregator | Semantics | Example KPI |
|---|---|---|
| **SNAPSHOT_FIELD** | Read a flat field at the latest snapshot ≤ period | K080 Tier 1 Capital |
| **SNAPSHOT_PATH** | Read a dotted path (`income_statement.net_interest_income`) | PBT, K005 |
| **RATIO_OF_FIELDS** | numerator_path / denominator_path × scale | NIM, ROA, CASA Ratio |
| **GROWTH_RATE** | (current_period − prior_period) / prior_period × 100 | Loan Book Growth, Deposit Growth |
| **SUM_LIST** | Sum a numeric field over a list of records | Disbursements (sum loan amounts) |
| **COUNT_LIST** | Count records, optionally filtered | Number of Business Borrowers |
| **MEAN_LIST** | Mean of a numeric field over a list | Channel Dormancy mean |
| **PERIOD_FILTER_THEN_SUM** | Filter records by period_field == period, then sum | Period-stamped balance computations |

8 aggregators — same count as per-staff (deliberate). Each is a pure function of `(source_data, rule, period) → (value, meta)`. Determinism, Decimal precision (28 digits) for monetary values, fail-closed on missing source.

### Honesty rules (inherited from Phase 1D and Mandatory Standard #11)

1. **No silent imputation.** A KPI with a missing source field returns `value=None` + `reason="missing_field:<path>"` in meta. NEVER zero. NEVER prior period.
2. **No silent period drift.** If the requested period has no record (snapshot stale, list empty), return `value=None` + `reason="no_record_for_period"` and surface the latest available period in meta. The caller decides whether to use stale data.
3. **GROWTH_RATE returns None on zero baseline.** `(x - 0) / 0` is undefined; never substituted with 100% or infinity.
4. **RATIO_OF_FIELDS returns None on zero denominator.** Same principle.
5. **List filters are explicit.** A bank-level rule's `period_field` is mandatory for list-shaped sources; missing this field in the rule is a registration error (rejected at load), not a silent full-list aggregation.

---

## Acceptance criteria

Phase 1E is closed when **all** of:

1. `utils/bank_aggregator.py` is shipped with all 8 aggregators implemented + self-tests
2. `data/bank_aggregation_rules.json` contains rules for all 37 bank-level KPIs (all `active: true`)
3. Each rule has been verified against live CBS-mock data (produces non-None values)
4. New API endpoint `/api/integration/bank_level/{period}` is wired with JWT + role-gating, matching the Phase 1D endpoint pattern
5. BSC engine consumes bank-level results alongside per-staff results into a single bank-level scorecard
6. **G144 audit gate** — `bank_level_aggregator_coverage` — passes at 37/37 = 100%
7. **G143 strict-flip preparation** — G143 reframed to compute `(per_staff_covered + bank_level_covered) / total_in_scope` so it lands at 100% when both pipelines are complete (the strict-flip itself remains a v10.130+ decision)
8. Audit at closure: 163+/163+ PASS (G144 added; existing gates unchanged)
9. Master prompt updated to v3.63+ with Phase 1E section
10. Phase 1E retrospective doc shipped as final batch

Anything short of all 10 means Phase 1E is not closed.

---

## Sub-campaign sequence

Following the canonical campaign pattern (planning batch → foundation → expansion → integration → audit → retrospective):

| Batch | Theme | Estimated lines | Audit gate impact |
|---|---|---|---|
| **v10.269** (this batch) | Phase 1E Charter doc + scope reconnaissance | ~400 (this doc) | None |
| v10.270 | Foundation: `utils/bank_aggregator.py` engine + 8 aggregator implementations + self-tests | ~600 | None (engine only) |
| v10.271 | Rules batch 1: 12 rules covering capital_adequacy + liquidity_metrics + mgmt_accounts (the high-leverage trio) | ~250 (rules JSON + tests) | None |
| v10.272 | Rules batch 2: 13 rules covering cbs_loans + cbs_deposits + cbs_fees + cbs_accounts + alm_liquidity | ~250 | None |
| v10.273 | Rules batch 3: 12 rules covering digital_channels + contact_centre + cybersecurity + esg_climate | ~250 | None |
| v10.274 | API + BSC wiring: `/api/integration/bank_level/{period}` + bsc_engine integration | ~400 | None |
| v10.275 | **G144 audit gate + G143 reframe + Phase 1E retrospective** (closure) | ~300 | **G144 NEW (164 total)**; G143 reframed |

Total: 7 batches. The Phase 1D retro estimated 5–8; this lands in the middle.

If a rules batch hits friction (e.g., a source file has unexpected shape and needs an adapter), it spawns a 0.5 batch within the sub-campaign — same pattern as the v10.253–v10.260 PG migration sub-sub-campaign, where DDL and migrators alternated.

---

## What this charter does NOT cover

Honest scope-limiting list:

1. **Bank-level forecasting** — projecting CAR/LCR forward in time. Engine produces actuals only. Forecasting is a separate concern (engine downstream, not pipeline).
2. **Reconciliation between bank-level and per-staff KPIs** — some KPIs (e.g., total disbursements) could in principle be computed both ways. We do not cross-validate. Each KPI is wired exactly once via exactly one pipeline (decided at rule-registration time).
3. **Branch-level aggregation** — between staff and bank levels. The retro flagged this as a future possibility. Out of scope here; Phase 1F if it ever happens.
4. **Daily snapshots** — most bank-level rules return monthly/quarterly snapshots based on the source's `as_at` cadence. Daily-resolution rules (e.g., daily NIM trend) are not in scope.
5. **Alerts on threshold breaches** — Phase 1E produces values. The smart-alerts engine (v8.4) already consumes them and decides what to alert on. We do not duplicate that logic here.
6. **PostgreSQL persistence of bank-level results** — bank-level rules read from JSON files and produce in-memory results. PG persistence (a `bank_kpi_actuals` table) is a future concern, similar to how v10.265 added persistence for CBK regulatory packages.
7. **Multi-tenant / multi-bank** — A2Z is single-tenant for Ecobank Kenya. Bank-level pipeline assumes single-bank source files. Future multi-tenant support would require source-file scoping and is not in scope.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Source file shape drift breaks rules silently | Rules declare `shape` explicitly (flat_snapshot / nested_snapshot / list_of_records); engine rejects shape mismatch at load time |
| `as_at` field name varies across sources | Each rule declares `period_field` explicitly; engine does not guess |
| Decimal precision loss on KES-billion values | All monetary aggregators use `Decimal` internally with `getcontext().prec=28`; output rounded by rule-declared `decimals` |
| Source file missing on production deployment | Engine returns `value=None` + `reason="source_file_not_found"`; G144 audit gate flags it; never crashes the pipeline |
| Two rules accidentally targeting the same KPI (one per-staff, one bank-level) | Registration check at module-load: a KPI cannot be in both `aggregation_rules.json` and `bank_aggregation_rules.json` |
| G144 ratchet drift (rule count silently shrinks) | G144 audit gate enforces increase-only baseline (same kaizen pattern as G163) |
| Bank-level scorecard breaks per-staff scorecard | BSC engine wires bank-level as a separate column dim; existing per-staff render unchanged |

---

## Spirit statements

1. **Bank-level KPIs are not afterthoughts.** They are the metrics the board actually reads. A platform that ships per-staff intelligence without bank-level aggregates is incomplete by design.

2. **Two pipelines, one BSC.** The architectural split between Phase 1D (per-staff) and Phase 1E (bank-level) is honest about the dimensional difference. Forcing them through one engine would either compromise the per-staff path or introduce silent dimensional drift. Two pipelines, one downstream consumer.

3. **No silent fallback. No silent imputation. No silent zero.** The Mandatory Standard #11 honesty discipline applies at the bank level too — possibly more, since bank-level errors flow into board reports. A None value with a reason is worth more than a fabricated zero.

4. **Audit-lock the new gate.** G144 is the kaizen ratchet that makes Phase 1E's coverage permanent. Adding rules can only grow the count; removing them must be deliberate, documented, and audit-baseline-acknowledged.

5. **Strict-flip is its own decision.** Reaching 100% G143 enables strict-flip; it does not require it. The strict-flip move (v10.130+ candidate) is a separate batch where the audit gate stops accepting < 100% as informational.

6. **Phase 1F is not Phase 1E.** Branch-level aggregation, daily resolution, multi-tenant support — all valid future work. None of it should bolt onto Phase 1E. Each deserves its own charter.

---

## Honest acknowledgements at charter time

1. **Charter is opinionated.** The 8-aggregator catalog is a design choice, not a derivation. A different team might split RATIO_OF_FIELDS into RATIO_PERCENT and RATIO_RAW, or merge MEAN_LIST and SUM_LIST under a single STATISTIC_OVER_LIST. The 8 chosen here match the 8 universal patterns from Phase 1D for symmetry.

2. **The 37-count is current.** New KPIs may be added to the library between this charter and Phase 1E closure. The acceptance criterion is "all bank-level KPIs in the library at closure time" — not "the 37 from this charter."

3. **No live FLEXCUBE testing.** As with Phase 1D, the bank-level pipeline reads CBS-mock data. The shape compatibility with real Ecobank FLEXCUBE 12 export is verified by the FLEXCUBE adapter (Phase 1B work), not by Phase 1E.

4. **G144 baseline at first ship is the ceiling, not the floor.** Per the kaizen discipline established by G161/G162/G163, the audit gate baseline locks the count at first-shipping. Future regressions cannot silently shrink coverage.

5. **No retroactive changes to G143.** G143 stays in its current informational-pass shape until v10.275, which adds the bank-level component. This avoids breaking existing audit baselines mid-sub-campaign.

6. **Strict-flip is still a v10.130+ move.** Even after Phase 1E closes, G143 strict-flip requires a separate decision. The pre-conditions become satisfied; the move itself remains explicit.

7. **66 consecutive clean batches at charter time.** v10.193 → v10.268 unbroken. This sub-campaign aims to extend that streak to 73+ at closure.

---

## What "closing the standards arc" looks like at the end

By v10.275:

- Phase 1D Integration Layer: closed (since v10.125)
- Phase 1E Bank-Level Pipeline: closed (this sub-campaign)
- G143: 131/131 = 100% (informational-pass, strict-ready maximum)
- G144: 37/37 = 100% (NEW kaizen ratchet for bank-level coverage)
- All 10 deferrals from Phase 1D retro: 7 closed (5 already closed since v10.125 + 2 from this sub-campaign — bank-level pipeline + G144); 3 remain open and openly named (React dashboard, library cleanup K028/K048, alm_liquidity legacy schema adapter — all explicitly out of Phase 1E scope)

The standards arc — defined as the integration layer reaching 100% KPI coverage with audit-locked discipline — closes at v10.275. The remaining 3 open items are well-scoped follow-ups, each documented with explicit non-scope rationale, available as future sub-campaigns or v11 main-track work.

That is what closure looks like. Not "everything is done" — that's never true. Closure is "every open item is either shipped or deliberately scoped out with a documented reason."

---

— v10.269 charter, May 2026
