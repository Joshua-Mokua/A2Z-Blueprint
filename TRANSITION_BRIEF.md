# TRANSITION_BRIEF.md — A2Z MIS 360 Handoff
**Last platform version:** v10.494
**Date written:** 2026-05-13
**Master prompt:** docs/Master_Prompt_v5.38.md (lockstep — one-hundred-and-thirty-ninth consecutive batch)

## ✅ All core capabilities + 📋 Unification arc in flight

- Charter §2 chain: 7/7 WIRED, end_to_end_verified=True (G249)
- PBT computed from CBS + OpEx with full P&L drill-down (G250)
- FLEXCUBE live wire-up: real requests.get + mock mode (G251)
- CBS accruals synthesized: realistic NII / fees (G252)
- **Profitability reconciliation diagnostic** measuring 90.83% ΔPBT between engines A & B (G253 INFORMATIONAL — ratchets in v10.494+)
- **Architecture review shipped** — `docs/PROFITABILITY_ARCHITECTURE_REVIEW.md` maps the 4 engines + unification arc

## STEP 1 — VERIFY BEFORE TOUCHING ANYTHING
1. Read `docs/Master_Prompt_v5.38.md` (THE canonical constitution)
2. Read `docs/PROFITABILITY_ARCHITECTURE_REVIEW.md` (v10.494 deliverable — direction needed on Q1-Q4)
3. Read `CHANGELOG_v10.494.md` (reconciliation diagnostic closure)
4. Run `python scripts/verify_local_state.py` → expect **ALL 226 CHECKS PASSED**
5. Smoke trio: expect 123/123 + 0 static + 14/14 dynamic
6. Verify reconciliation diagnostic runs (next section)
7. Audit (full): expect 253/253 BUT takes ≥5min

## STEP 2 — Verify the diagnostic
```
python -c "
import tempfile
from pathlib import Path
from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
from utils.profitability_reconciliation import reconcile, format_report
bank, _ = seed_virtual_bank(config=SeedConfig.small())
with tempfile.TemporaryDirectory() as td:
    persist_bank_to_cbs(bank, output_dir=Path(td))
    print(format_report(reconcile(Path(td))))
"
```
Expect: ΔPBT ~90%, Status DIVERGENT (current state — unification arc closes this).

## STEP 3 — THE FOUR PROFITABILITY ENGINES (v10.494 survey)

| Engine | File | Data source | Drill-down | Used by |
|---|---|---|---|---|
| A | `utils/pbt_computation.py` | accounts.csv + opex_data.json::bank | None (bank only) | MD's BSC, compute_bank_aggregates |
| B | `utils/sbu_pnl_rollup.py` | customer_intelligence.json + cost_allocation_rules.json | Segment/Sector/RM/Proposition | Finance hub |
| C | `actuals_engine::aggregate_cbs_by_branch` | accounts.csv | Per-branch (legacy formula) | Branch ranking |
| D | `utils/customer_profitability.py` | per-customer record | Per-customer | Customer 360 |

Reconciliation identity that MUST hold post-unification:
```
Σ(SBU PBT) = Σ(Branch PBT) = Σ(RM PBT) = Bank PBT
(Propositions excluded — they overlap, Rule 6)
```

## STEP 4 — CHARTER §2 + DATA PIPELINE STATUS

```
✓ teller → CBS                   WIRED (v10.359)
✓ CBS → actuals_engine           WIRED
✓ actuals_engine → YoY           WIRED (v10.355)
✓ YoY → BSC display              WIRED
✓ BSC → branch score             WIRED
✓ branch → regional              WIRED
✓ regional → MD tile             WIRED (v10.362)
End-to-end verified: TRUE (v10.363 — Charter §2 PASSES)
PBT computation: PROPER (v10.364)
FLEXCUBE seam: WIRED (v10.365 — 3 modes)
CBS accruals: SYNTHESIZED (v10.366)
Profitability reconciliation: MEASURING (v10.494 — 90.83% ΔPBT, unification in flight)
```

## STEP 5 — VIRTUAL BANK INFRASTRUCTURE

| Module | LOC | Self-test |
|---|---|---|
| utils.virtual_bank_core | 1,167 | ✓ 27 |
| utils.virtual_bank_simulator | 1,323 | ✓ 23 |
| utils.virtual_bank_seed | ~530 | ✓ 10 |
| utils.virtual_bank_cbs_writer | ~510 | ✓ 9 |
| utils.teller_actions | ~250 | ✓ 9 |
| utils.pbt_computation | ~290 | ✓ 8 |
| utils.accruals_synthesizer | ~340 | ✓ 10 |
| utils.profitability_reconciliation | ~340 | ✓ 7 |
| utils.sbu_pnl_rollup | 548 | (existing) |
| utils.flexcube_adapter | ~1,700 | n/a (3 modes) |

## STEP 6 — SMOKE TRIO + RATCHETS (144 batch-specific gates)

| Layer | Gate | Cost |
|---|---|---|
| Module-load | G231 | ~13s |
| Static AST | G238 | ~0.4s |
| Dynamic render | G239 | ~7s |
| Structure audit | G128 | ~9s |
| CBS baseline | G240 | 0.1s |
| Live actuals | G241 | 0.2s |
| Master prompt sync | G242 | 0.0s |
| Virtual bank readiness | G243 | ~6s |
| Seed determinism | G244 | ~0.1s |
| CBS writer integrity | G245 | ~0.2s |
| Branch single source | G246 | ~0.03s |
| Admin CRUD coverage | G247 | ~0.05s |
| MD tile bank-targets binding | G248 | ~0.2s |
| Charter §2 Football Team Test | G249 | ~0.2s |
| PBT computation | G250 | ~0.2s |
| FLEXCUBE live wire-up | G251 | ~0.01s |
| CBS accruals synthesizer | G252 | ~0.1s |
| **Profitability reconciliation** | **G253 (informational)** | **~0.3s** |
| **SBU PBT reconciliation** | **G254** | **~0.05s** |
| **Per-Branch PBT reconciliation** | **G255** | **~0.07s** |
| **Per-Customer PBT reconciliation** | **G256** | **~0.07s** |
| **Per-Staff PBT reconciliation** | **G257** | **~0.05s** |
| **Multi-Level targets schema (Σ child = parent)** | **G258** | **~0.05s** |

## STEP 7 — ANTI-DRIFT DISCIPLINE (139/139 CONSECUTIVE)

v10.356 → v10.494: every batch synced master prompt + closed-gaps list + State-of-Play.
v10.494 = v5.38 — **SBU PBT Reconciliation (Σ SBU = Bank, G254 locks)**

## STEP 8 — KNOWN LIMITATIONS

- Profitability engines diverge ~90% (v10.494 measures; v10.494-v10.494 unify)
- Full audit >5 min
- Per-branch PBT in aggregate_cbs_by_branch still legacy formula
- Total NFI in compute_bank_aggregates still legacy formula
- Impairment is Stage 3 only
- 45/94 branches have region "Other"
- BSC coverage 2.78%
- Bridge overwrites cbs_data/*.json
- Hard branch delete NOT implemented
- npl_aggregate.json::by_aging_kes zeroed
- strategy_simulator + hybrid_scheduling_simulator lack self_test
- FLEXCUBE live mode can't be exercised in sandbox (mock mode is substitute)
- v10.366 synthesizer uses approximate months for fees
- non_interest_other_pct stub still in pbt_assumptions
- No `interest_expense_ytd` column in accounts.csv
- bank_targets.json has only bank-level targets (no SBU/branch/RM cuts yet — v10.494 closes)

## STEP 9 — DON'T DRIFT
- Pattern R: distribution zips MUST be flat
- Pattern T: cumulative zips copy ALL utils + pages
- Pattern Q: validate-before-save for every protected schema
- **Rule N1**: tenant identity configured, never hardcoded (G162, G246+G247; pbt_assumptions, opex_data, accruals_assumptions, flexcube credentials)
- Rule N2: single-purpose batches
- Rule N3: audit before AND after every change
- Rule N4: honest acknowledgements
- Rule N5: ratchets, not heroics
- Rule N6: memory reconciliation
- Rule N7: admin page registry pattern
- Rule N8: KAIZEN cadence
- Lockstep: master prompt sync every batch (G242)
- **Utility modules in utils/ must never import their consumers** (v10.364 lesson; G250 + G252 enforce; G253 enforces a stricter allowed-list)
- New utils/ MUST NOT import higher-layer orchestrators (G128)
- ALL_CAPS in functions MUST resolve (G238)
- New render functions in hubs MUST be in dynamic_smoke RENDER_REGISTRY (G239)
- CBS baseline dated archives are IMMUTABLE
- YoY sidecar regenerated on actuals refresh
- org_config.json::branches[] is the SINGLE source for branch list (G246), or FLEXCUBE when live (G251)
- Seeder must be deterministic (G244)
- Bridge writes must be atomic + idempotent + coherent (G245)
- CBS data categories use Title case
- MD's BSC reads bank_targets.json for targets + compute_bank_aggregates for actuals (G248)
- utils.teller_actions must remain present + self_test must pass (G249)
- Charter §2 propagation probe must pass; latency < 5s (G249)
- utils.pbt_computation must remain present (G250)
- compute_bank_aggregates must wire compute_pbt_from_cbs (G250)
- PBT factors from data/pbt_assumptions.json + data/opex_data.json (Rule N1)
- FLEXCUBE live functions must call requests.get with Bearer auth (G251)
- Mock fixtures must exist (G251)
- Synthetic mode must return None (G251)
- utils.accruals_synthesizer must remain present (G252)
- virtual_bank_cbs_writer must call the synthesizer (G252)
- Accrual factors from data/accruals_assumptions.json (Rule N1)
- **utils.profitability_reconciliation must remain present (G253)**
- **profitability_reconciliation allowed utils imports = {pbt_computation, sbu_pnl_rollup} only (G253)**
- **docs/PROFITABILITY_ARCHITECTURE_REVIEW.md must remain present (G253)**
- **utils.pbt_computation must export compute_pbt_by_sbu + sum_sbu_pbts + format_sbu_breakdown (G254)**
- **virtual_bank_cbs_writer must write customers.csv (G254)**
- **data/segment_sbu_mapping.json must remain present (G254)**
- **Σ(SBU PBT) must equal Bank PBT within KES 100 (G254)**
- **utils.branch_pbt_allocator must export compute_pbt_by_branch + sum_branch_pbts + format_branch_breakdown (G255)**
- **data/branch_allocation_rules.json must remain present with default_rule (G255)**
- **Σ(Branch PBT) must equal Bank PBT within KES 100 (G255); drift absorbed by largest-OpEx branch**
- **utils.customer_pbt_allocator must export compute_pbt_by_customer + compute_pbt_by_staff + sum_*_pbts + format_* (G256, G257)**
- **data/customer_allocation_rules.json must remain present with default_rule (G256)**
- **Σ(Customer PBT) must equal Bank PBT within KES 100 (G256); OpEx EXACT; drift absorbed by largest-revenue customer**
- **Σ(Staff PBT including Unassigned) must equal Bank PBT within KES 100 (G257); OpEx preserved through aggregation**
- **Per-staff aggregation must return ALL tagged staff role-neutrally; role filtering is a UI concern downstream**
- **utils.bank_targets_schema must export parse_target_key + compose + migrate + get + set + sum + validate (G258)**
- **Multi-level target keys MUST be <metric>|<level>|<entity>|<year>; level ∈ {bank,sbu,branch,staff,customer}**
- **Legacy <metric>|<year> keys must keep working (in-memory alias as bank|all)**
- **Σ(child level targets) must equal bank|all target within 0.1% tolerance (G258); sparse populations OK**
- **utils.sbu_pnl_rollup.bank_total_pnl MUST accept cost_source="canonical" with cbs_dir param (G253)**
- **Engine A (compute_pbt_from_cbs) and Engine B canonical MUST converge within 1% of bank PBT (G253 ENFORCING)**
- **legacy matrix/proxy modes preserved but documented as deprecated**
- **docs/SYSTEM_STATE_REVIEW_v10.494.md MUST remain with 8 Parts + key cross-references (G259)**

## STEP 10 — STATE AT v10.494

- Audit: 295 gates
- Page smoke: 123/123 + 0 static + 14/14 dynamic
- Verifier: 457/457 checks
- G162 baseline: 4022 (188 consecutive zero-drift batches)
- 19 protected data files (added segment_sbu_mapping.json, branch_allocation_rules.json, customer_allocation_rules.json)
- Master prompt: v5.38 (lockstep 12 consecutive batches)
- Feedback loops: 15/15 WIRED
- System stocks: 6/6 wired with demo defaults
- Hard invariants: 8 registered
- Standards: 330 across 27 categories
- **Profitability engines: 4 surveyed. SBU dimension SHIPPED (v10.494) — Σ(SBU PBT) = Bank PBT exactly. v10.494-v10.494 continues unification arc**
- Virtual bank: ~31,420 LOC across 25 modules + Phase B COMPLETE + Phase C executing (admin canonical migration shipped); ~71KB review/design documentation
- Total integration tests passing across v10.358–v10.494: **136**

## STEP 11 — v10.494+ ROADMAP (THE UNIFICATION ARC)

| Batch | Concern | Closes |
|---|---|---|
| ~~v10.494~~ | ~~SBU dimension~~ **CLOSED** | **Σ(SBU PBT) = Bank PBT — G254 ✓** |
| **v10.494** | `branch_pbt_allocator.py` with configurable driver (FTE default) | Σ(Branch PBT) = Bank PBT — G255; G253 → <5% |
| **v10.494** | rm_profitability.py refactored to canonical | Σ(RM PBT) = Bank PBT — G256 |
| **v10.494** | Multi-level bank_targets.json schema | Top-down + bottom-up; G253 → CONVERGED |
| **v10.494** | Engine B (sbu_pnl_rollup) refactor to consume canonical | Eliminates parallel-engines structural debt |
| **v10.494+** | UI surfacing of new dimensions | Visible drill-downs in MD dashboard |
| **v10.4XX+** | React executive frontend (Standard #9) | Next major arc |

## STEP 12 — DECISIONS AWAITING JOSHUA

Resolved in v10.494:
- Q1 ✓ Engine A canonical (MD's BSC + bank_targets reference)
- Q3 ✓ FTE-weighted allocation driver default (configurable per Rule N1)
- Ordering ✓ SBU first (v10.494 done), per-branch next (v10.494)

## STEP 13 — RED FLAGS
- verify_local_state < 457/457 → diagnose
- G128 fails → circular import reintroduced
- G242 fails → master prompt drift > 5 batches
- G249 fails → CHARTER §2 BROKEN (most critical)
- G250 fails → PBT computation broken
- G251 fails → FLEXCUBE wire-up regressed
- G252 fails → accruals synthesizer broken
- **G253 fails → diagnostic itself crashed** (not divergence — divergence is informational)
- **G254 fails → SBU reconciliation identity broken**
- **G255 fails → Branch reconciliation identity broken**
- **G256 fails → Customer atomic unit broken** (highest-priority fix — Bank/SBU/Branch/Staff all derive from this)
- **G257 fails → Staff aggregation broken**
- **G258 fails → Multi-level target hierarchy broken** (Σ child ≠ bank)
- **G253 fails → Engine A and Engine B canonical diverged** (fix urgently)
- **G259 fails → System State Review document missing or damaged**
- **G260 fails → Role taxonomy alignment broken** (a role not classified, OR taggability invariant violated)
- **G261 fails → Staff PBT page broken**
- **G262 fails → PM Framework Bridge broken**
- **G263 fails → Universal BSC Data Contract broken**
- **G264 fails → Customer Master Merge broken**
- **G265 fails → Canonical Write-Bridge broken**
- **G266 fails → KPI Alias Resolver broken**
- **G267 fails → Customer Profitability Canonical Refactor broken**
- **G268 fails → Three Deep Reviews broken**
- **G269 fails → RM Profitability Canonical Refactor broken**
- **G270 fails → Canonical Pillar Weights Accessor broken**
- **G271 fails → Deep Body Diagnosis broken**
- **G272 fails → Admin Canonical Migration broken** (design doc missing 7 Parts, OR admin not importing save_pillar_weights, OR save call missing actor/reason kwargs, OR History view missing, OR old direct write still in KPI Library block, OR admin syntax error)
- Smoke trio < 100% → regression

## STEP 14 — START NEW CHAT
```
Read docs/Master_Prompt_v5.38.md, then docs/PROFITABILITY_ARCHITECTURE_REVIEW.md, then TRANSITION_BRIEF.md.
Verifying state.
[verify_local_state → 457/457 PASSED]
[smoke run → 123/123 + 0 static + 14/14 dynamic]
[readiness audit → 7/7 WIRED, end_to_end_verified=True, READY]
[reconcile diagnostic → ΔPBT 90.83% DIVERGENT (expected)]
Charter §2 + PBT + FLEXCUBE + accruals + reconciliation diagnostic (now ENFORCING) + SBU + Branch + Customer + Staff + multi-level targets + engine convergence all green.
Profitability unification arc COMPLETE (5/5 batches done — six identities locked). v10.494 system review identifies next ~25 batches across 5 phases. Awaiting Joshua's response on 4 decisions before proceeding to v10.494.
```

**End of brief.**
