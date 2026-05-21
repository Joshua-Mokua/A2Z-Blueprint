# Changelog — v10.367 Profitability Reconciliation Diagnostic

**Date:** 2026-05-13
**Phase:** 4 (fifty-second arc — measurement-first batch for the profitability unification)
**Audit:** G253 added (INFORMATIONAL — passes whenever diagnostic runs cleanly; reports ΔPBT as metric)
**Tests:** 15/15 PASSED in `test_v10367_profitability_reconciliation.py`; 121 prior tests unchanged = **136 total**
**Page smoke:** 123/123 PASS + 0 static findings + 14/14 dynamic renders pass
**Verifier:** 226/226 checks pass on a clean extract
**G162 baseline:** 4022 (61 consecutive zero-drift batches)
**Master prompt:** v4.10 → v4.11 (lockstep — twelfth consecutive batch)

---

## Your ask

> "proceed, note: we also had down top which ultimately should equal, as per our plan
> we need to show case the SBU profitability as well, we had propositions overlapping,
> Profitability per branch, sales team etc review the entire structure as we proceed."

Then: "proceed" (after I presented the survey + proposed diagnostic-first batch).

## What the survey surfaced

A2Z has **four parallel profitability engines**, each rolling up from different
data sources, only loosely aware of each other:

| Engine | File | Data source | Drill-down | Used by |
|---|---|---|---|---|
| A | `utils/pbt_computation.py` (v10.364) | accounts.csv + opex_data.json::bank | None (bank-level) | MD's BSC |
| B | `utils/sbu_pnl_rollup.py` (v10.338) | customer_intelligence.json + cost_allocation_rules.json | Segment / Sector / RM / Proposition | Finance hub |
| C | `actuals_engine::aggregate_cbs_by_branch` | accounts.csv | Per-branch | Branch ranking pages |
| D | `utils/customer_profitability.py` | per-customer record | Per-customer | Customer 360 |

Live probe of Engine A vs Engine B on the seeded bank:

```
                                Engine A         Engine B
PBT                       KES -7,901,272,160   KES -724,284,661
Revenue                          -1,272,160      7,267,354,081
Indirect Cost (OpEx)          7,900,000,000      5,750,000,000
Time horizon                          ytd            annual
Customer basis                cbs_accounts     customer_intelligence

ΔPBT = KES -7.18B (90.83%)    Status: DIVERGENT
```

Reasons documented in the diagnostic output:
- **Revenue diverges** because Engine A reads CBS YTD accruals; Engine B uses
  CLV-derived customer proxy. Different inputs entirely.
- **OpEx allocation differs** — Engine A reads `opex_data.json::bank.total_opex_kes_b`
  (single bucket); Engine B uses matrix-allocated quarterly OpEx (1.975B per quarter).
- **Customer basis differs**: A reads cbs_accounts (operational, 100 in seed);
  B reads customer_intelligence (3,206 customers).

## What v10.367 delivered

### `utils/profitability_reconciliation.py` — diagnostic module

Runs both engines side-by-side, normalizes time horizons, surfaces reasons for divergence:

```python
@dataclass
class EngineSnapshot:
    engine_id: str
    revenue: Decimal
    direct_cost: Decimal
    indirect_cost: Decimal
    impairment: Decimal
    pbt: Decimal
    time_horizon: str       # 'annual' | 'quarterly' | 'ytd'
    customer_basis: str     # 'cbs_accounts' | 'customer_intelligence'
    notes: List[str]
    raw: Dict[str, Any]

@dataclass
class ReconciliationReport:
    engine_a: EngineSnapshot
    engine_b: EngineSnapshot
    delta_pbt_kes: Decimal
    delta_revenue_kes: Decimal
    delta_opex_kes: Decimal
    delta_pbt_pct: float
    reasons: List[str]
    status: str             # 'CONVERGED' | 'TOLERANCE' | 'DIVERGENT'
    tolerance_pct: float
```

**Status thresholds:**
- `CONVERGED`: ΔPBT < 1% — ratchet target for v10.372
- `TOLERANCE`: ΔPBT < 5% — ratchet target for v10.370
- `DIVERGENT`: ΔPBT ≥ 5% — current state (v10.367)

**Module purity:** allowed `utils.*` imports are exactly `{pbt_computation, sbu_pnl_rollup}` — the engines this module legitimately consumes. G253 enforces this set via AST scan; any other upward import fails the gate.

### `docs/PROFITABILITY_ARCHITECTURE_REVIEW.md` — structural review document

The core v10.367 deliverable. Contains:
- Current state of all four engines (what each reads, computes, drives)
- The reconciliation identity that must hold: `Σ(SBU) = Σ(Branch) = Σ(RM) = Bank PBT`
- Why propositions are excluded (Rule 6 — they overlap by design)
- What `opex_data.json::by_sbu` already gives us (Σ SBU PBT = 5.3B ≈ bank PBT 5.4B — reconciles in config but not in any engine)
- The five-batch unification arc:
  - **v10.368 — Align data sources.** Make sbu_pnl_rollup walk same accounts.csv as pbt_computation
  - **v10.369 — Add SBU dimension to canonical.** `compute_pbt_from_cbs(by_sbu=True)` returns per-SBU components. G254 locks Σ(SBU) = Bank
  - **v10.370 — Per-branch allocation engine.** Admin-configurable driver. G255 locks Σ(Branch) = Bank. **G253 ratchets to ΔPBT < 5%**
  - **v10.371 — Per-RM canonical refactor.** G256 locks Σ(RM) = Bank
  - **v10.372 — Multi-level bank_targets.json schema.** `PBT|<level>|<entity>|<year>` keys. **G253 ratchets to CONVERGED (<1%)**

Plus open design questions Q1-Q4 awaiting Joshua's direction:
- Q1: Which engine is canonical? (Recommendation: Engine A — matches MD's BSC + bank_targets.json)
- Q2: Proxy revenue sunset cadence? (Recommendation: phase out over v10.368→v10.371)
- Q3: Per-branch allocation driver default? (Recommendation: FTE-weighted, configurable)
- Q4: Proposition visibility for MD? (Recommendation: visible but labeled "informational, doesn't sum")

### `G253` — informational gate

Passes whenever the diagnostic runs cleanly. The current ΔPBT is reported in the
gate's `summary` as informational metadata:

```
G253: 0.32s, passed=True
Summary: ... | Current ΔPBT = 90.83% (status: DIVERGENT) |
         v10.368-v10.372 unification arc will reduce this to <5%
```

The gate **does not fail** on divergence. This is deliberate — the engines are
known-divergent in v10.367. The point is to measure and surface; ratcheting to
require convergence happens in v10.370 and v10.372 when the engines are actually
aligned.

### `tests/integration/test_v10367_profitability_reconciliation.py` — 15 tests across 5 sections

Module surface, architecture review doc presence, engine snapshots, normalization,
full `reconcile()` end-to-end, JSON serialization, reasons surface causes, G253
passes + reports delta in summary, G253 in gates list, self-test passes.

## Files changed

| File | Change |
|---|---|
| `utils/profitability_reconciliation.py` | **NEW** — diagnostic module |
| `docs/PROFITABILITY_ARCHITECTURE_REVIEW.md` | **NEW** — structural review (core deliverable) |
| `scripts/audit.py` | **NEW** `gate_profitability_reconciliation` (G253) |
| `scripts/verify_local_state.py` | Extended to 226 checks |
| `tests/integration/test_v10367_profitability_reconciliation.py` | **NEW** — 15 tests |
| `docs/Master_Prompt_v4.11.md` | **NEW** — lockstep bump from v4.10 |

**No engine changes.** Engines A, B, C, D are untouched. v10.367 is pure measurement + roadmap.

## Verified outcome

| Metric | Value |
|---|---|
| Engines surveyed | 4 |
| ΔPBT (current state) | 90.83% — DIVERGENT |
| Diagnostic module size | ~340 LOC, 7 self-tests |
| Allowed utils imports | `{pbt_computation, sbu_pnl_rollup}` only |
| Audit gates | 252 → **253** (G253 informational) |
| Charter §2 (G249), PBT (G250), FLEXCUBE (G251), Accruals (G252) | **all still pass** |
| Page smoke | 123/123 + 0 static + 14/14 dynamic (preserved) |
| Tests | +15 in v10.367; **136 total across v10.358–v10.367** |
| Verifier | 218 → **226 checks** |
| Master prompt | v4.10 → **v4.11** — lockstep (12 consecutive batches) |
| G162 baseline | 4022 (**61 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **The architecture review document is the primary deliverable.** The diagnostic module is the secondary deliverable that proves the review's claims with running code. v10.367 is unusual in that the doc carries more weight than the code; that's appropriate when the task is "review the entire structure" rather than "ship a feature".

2. **G253 doesn't actually catch divergence today.** The 90.83% divergence is informational, not a failure. This is intentional — failing the gate today would block every batch with no path forward, since the engines were *designed* divergent and need v10.368-v10.372 to align. The gate exists to measure; ratcheting happens after alignment.

3. **The five-batch unification arc is a plan, not a commitment.** Joshua may direct a different ordering — e.g., prioritize v10.369 (SBU dimension) first because `opex_data.json::by_sbu` is already populated. Or skip v10.371 (per-RM) if rm_profitability.py's existing methodology is good enough. The review surfaces the structure; he chooses the order.

4. **Recommendation in Q1 (Engine A as canonical) is debatable.** Engine A has the advantage of matching the MD's BSC + bank_targets.json, and matching what FLEXCUBE will report in production. Engine B has the advantage of being more sophisticated (matrix allocation, drill-down already wired). Engine A is recommended because the *single source of truth* for "what is the bank's PBT" must be CBS-derived (operational). But Engine B's machinery (rollup_by_segment, etc.) should be preserved and refactored to consume from Engine A's per-account data.

5. **Q4 (proposition visibility) is a UX question, not a data question.** The data already handles it correctly (Rule 6 in sbu_pnl_rollup.reconcile_to_bank). Whether the MD sees a "Propositions" tab in their dashboard is product design.

6. **The diagnostic's `_normalize_to_annual` is approximate.** Engine A is YTD (date-dependent); Engine B is quarterly (×4 to annualize). YTD isn't strictly comparable to annualized quarterly — Q1 YTD × 1 ≠ Q3 YTD × (4/3) ≠ Q1 quarterly × 4. The normalization is "good enough" for measuring the structural gap, but exact reconciliation requires the engines to share the same time semantics. v10.368+ should align time semantics too.

7. **`reasons` list is heuristic.** The diagnostic looks for revenue divergence >1M, OpEx divergence >100M, customer-basis mismatch, impairment-treatment mismatch. Real reasons (matrix allocation method, proxy uplift factors, etc.) are deeper. The list provides direction, not root cause.

8. **No regression risk.** v10.367 doesn't modify any engine — Engines A, B, C, D are byte-identical to v10.366. The 121 prior tests continue to pass without modification.

9. **The review document is opinionated.** It picks a canonical engine, recommends a default allocation driver, recommends sunsetting proxy mode. These are recommendations, not unilateral decisions. If Joshua disagrees with any of them, the unification arc adjusts accordingly. The document is the conversation starter, not the conversation closer.

10. **The diagnostic could grow.** Future enhancements: per-SBU reconcile (once v10.369 ships), per-branch reconcile (once v10.370 ships), per-RM reconcile (v10.371), target-actual reconcile (v10.372). G253 ratchets at each step. By v10.372, G253 verifies *full* multi-level reconciliation.

11. **Rule N2 held.** v10.367 is single-purpose: measure the gap + propose the path. Did not start implementing v10.368+. Each future batch is its own commit.

12. **Rule N3 (audit before AND after) is what produced this batch.** I almost shipped v10.367 as "per-branch PBT allocation engine" until Joshua's prompt made me audit the existing landscape. The survey revealed I'd have been building a third engine that doesn't reconcile with the other two. Surveying first prevented the mistake. This is what Rule N3 is for.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10367_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 226 CHECKS PASSED**
5. **Read `docs\PROFITABILITY_ARCHITECTURE_REVIEW.md`** — the core deliverable of this batch. Direction on Q1-Q4 + unification ordering shapes v10.368+.
6. **See the diagnostic output:**
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
7. Read `docs\Master_Prompt_v4.11.md` — twelfth consecutive lockstep batch.
8. (Optional, takes >5min) Run audit → expect **253/253 PASS**

## Decision points awaiting your direction

Before v10.368, please indicate:

1. **Q1 (canonical engine):** Engine A as canonical bank PBT, with Engine B refactored to drill-downs only? Or alternative?
2. **Q3 (default allocation driver):** FTE-weighted as v10.370 default? Or revenue-weighted? Or hybrid?
3. **Ordering:** Run v10.368 (align data sources) first, or jump to v10.369 (SBU dimension) since opex_data already has by_sbu?

Any of those answers + "proceed" gets v10.368.

## v10.368+ roadmap (assuming current ordering)

| Batch | Concern | Closes |
|---|---|---|
| **v10.368** | Align Engine B to walk same accounts.csv as Engine A | Common customer basis; ΔRevenue starts to close |
| **v10.369** | `compute_pbt_from_cbs(by_sbu=True)` + `opex_data::by_sbu` | Σ(SBU PBT) = Bank PBT — G254 |
| **v10.370** | `branch_pbt_allocator.py` with configurable driver | Σ(Branch PBT) = Bank PBT — G255; G253 ratchets to <5% |
| **v10.371** | rm_profitability.py refactored to canonical | Σ(RM PBT) = Bank PBT — G256 |
| **v10.372** | Multi-level bank_targets.json schema extension | Top-down + bottom-up reconcile at every level; G253 → CONVERGED |
| **v10.373+** | UI surfacing of new dimensions in MD dashboard | Visible drill-downs |

**The diagnostic is in place. The architecture is documented. v10.368+ executes the plan.**
