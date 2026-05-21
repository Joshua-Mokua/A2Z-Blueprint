# Changelog — v10.370 Per-Customer + Per-Staff PBT (Atomic Unit)

**Date:** 2026-05-13
**Phase:** 4 (fifty-fifth arc — third unification step; the atomic unit lands)
**Audit:** G256 + G257 added (locks Σ(Customer PBT) = Bank PBT; Σ(Staff PBT) = Bank PBT)
**Tests:** 18/18 PASSED in `test_v10370_customer_staff_reconciliation.py`; 167 prior tests unchanged = **185 total**
**Page smoke:** 123/123 PASS + 0 static findings + 14/14 dynamic renders pass
**Verifier:** 256/256 checks pass on a clean extract
**G162 baseline:** 4022 (64 consecutive zero-drift batches)
**Master prompt:** v4.13 → v4.14 (lockstep — fifteenth consecutive batch)

---

## Your ask

> "proceed. Note: at branch level we also do have business teams comprising BRMs, SROs, ROs these too have portfolios, however even other branch staff e.g tellers are also tagged accounts, i am still thinking how we shall treat their profitability. I need to drill this down to profitability per customer ultimately"

The framing reshapes v10.370: per-customer is now established as the **atomic unit** (the foundational ground truth), and per-staff is the thin Σ aggregation on top. The teller-vs-RM question becomes a UI filter on top of role-neutral data, not a data architecture problem.

## The reconciliation tree (now four-deep)

```
Per-customer PBT (ATOMIC — v10.370)
   │
   ├─ Σ over all customers              = Bank PBT       (v10.364, G250)
   ├─ Σ over customers in SBU/segment   = SBU PBT        (v10.368, G254)
   ├─ Σ over customers in branch        = Branch PBT     (v10.369, G255)
   └─ Σ over customers tagged to staff  = Staff PBT      (v10.370, G257 NEW)
                                            │
                                            ├─ G256 (NEW): Σ(Customer) = Bank
                                            └─ G257 (NEW): Σ(Staff) = Bank
```

Four identities, all locked. Customer is the atom; everything else derives.

## What v10.370 delivered

### `utils/customer_pbt_allocator.py` — NEW (~530 LOC, 11 self-tests)

Pure module. Zero upward `utils.*` imports beyond `pbt_computation` (legitimate downward dependency). Self-test uses hand-rolled CSV fixtures per the v10.364 lesson.

**Exports:**

| Function | Purpose |
|---|---|
| `compute_pbt_by_customer(cbs_dir, allocation_rule=None)` | Per-customer PBT (atomic unit) → `Dict[CIF, PBTComponents]` |
| `sum_customer_pbts(customer_pbts)` | Sum to bank total (G256 verification) |
| `compute_pbt_by_staff(cbs_dir, customer_pbts=None)` | Per-staff = Σ over portfolio → `Dict[staff_code, PBTComponents]` |
| `sum_staff_pbts(staff_pbts)` | Sum to bank total (G257 verification) |
| `format_top_customers(customer_pbts, top_n)` | Top + bottom customers readout |
| `format_staff_breakdown(staff_pbts, top_n)` | Top staff readout |
| `_aggregate_customers_from_csv(cbs_dir)` | Internal: walk accounts.csv, group by CIF |
| `_load_customer_rm_lookup(cbs_dir)` | Internal: read customers.csv for rm_code |
| `_compute_customer_allocation_shares(...)` | Internal: per-rule share calculation |

### Four allocation rules in `data/customer_allocation_rules.json` (Rule N1)

| Rule | Behavior |
|---|---|
| **`revenue_weighted`** (default) | Customer's OpEx share = their revenue share of total. Standard activity-based costing — aligns OpEx with value generated |
| `balance_weighted` | Customer's OpEx share = their (deposits + loans) footprint share. Reflects capital tied up |
| `equal` | Split evenly across customers. Sanity check / diagnostic only |
| `hybrid` | 50% revenue + 50% balance, weights configurable |

### THE FOUR IDENTITIES (all enforced)

On the seeded 100-customer bank:

```
Bank PBT (compute_pbt_from_cbs):          KES -7,901,267,033
   │
   ├─ Σ SBU PBT     (G254):              KES -7,901,xxx,xxx   (delta ≤1, OpEx exact)
   ├─ Σ Branch PBT  (G255):              KES -7,901,xxx,xxx   (delta ≤5, OpEx exact)
   ├─ Σ Customer PBT (G256 NEW):         KES -7,901,267,039   (delta 6 KES, OpEx EXACT)
   └─ Σ Staff PBT   (G257 NEW):          KES -7,901,267,039   (delta 6 KES, OpEx EXACT)
```

The `test_v10370_all_four_rollups_reconcile` test exercises all four together against bank total within KES 200 tolerance (2× per-rollup tolerance), so any future regression that breaks one of them fails this test immediately.

### Joshua's staff-role framing — handled via separation of concerns

The CHANGELOG quote: *"at branch level we also do have business teams comprising BRMs, SROs, ROs these too have portfolios, however even other branch staff e.g tellers are also tagged accounts, i am still thinking how we shall treat their profitability."*

The design separates two concerns:

**Data engine (role-neutral):** `compute_pbt_by_staff` returns ALL staff codes that appear in `customers.csv::rm_code`. No role filtering. The reconciliation identity holds regardless of whether a staff_code belongs to a BRM (portfolio owner) or a teller (service tagged).

**UI/reporting (role-aware):** The downstream UI joins each `staff_code` against `users.json::role` (or `hr.json`) to filter. Examples:

- *"Show portfolio profitability"* → filter to roles ∈ {BRM, SRO, RO, RM} → those staff are profit-responsible; show their PBT prominently
- *"Show service-cost attribution"* → filter to roles ∈ {Teller, CSO, BOS} → those staff don't own customer relationships but service transactions; show as cost centers not profit centers
- *"Show all tagged staff"* → no filter; debugging / audit view

This separation lets the data engine remain stable while UI requirements evolve. v10.373+ adds the role-aware UI on top.

### The `Unassigned` bucket

Customers in `customers.csv` with empty `rm_code` (or whose CIF appears in accounts.csv but not customers.csv) land in the `"Unassigned"` staff bucket. In production this would surface data-quality issues (every customer should have a tagged RM). The bucket preserves the reconciliation identity — every customer's PBT is accounted for somewhere.

### `G256` + `G257` — locked identities

**G256** verifies:
1. `compute_pbt_by_customer` + canonical exports present
2. `data/customer_allocation_rules.json` exists with valid `default_rule`
3. End-to-end: `Σ(Customer PBT)` within KES 100 of bank PBT
4. OpEx reconciles EXACTLY (drift-absorbed)

**G257** verifies:
1. `compute_pbt_by_staff` returns multi-staff dict
2. `Σ(Staff PBT)` within KES 100 of bank PBT
3. OpEx preserved through staff aggregation (sum identity, no rounding)

Both gates cost ~0.05-0.5s isolated.

### Tests — 18/18 across 6 sections

**Section 1 (module + config):** module surface, revenue_weighted as default (correct per "standard activity-based costing"), self_test passes

**Section 2 (per-customer correctness):** seeded bank produces 100+ customers, revenue_weighted correctly distributes (10x revenue → 10x OpEx)

**Section 3 (THE CUSTOMER IDENTITY):** Σ(Customer PBT) == Bank PBT, Σ(Customer OpEx) == Bank OpEx EXACTLY, identity holds across all 4 rules

**Section 4 (THE STAFF IDENTITY):** staff aggregation correct, Σ(Staff PBT) == Bank PBT, staff OpEx reconciles exactly, per-staff = Σ over portfolio (verified directly), Unassigned bucket catches unmapped customers

**Section 5 (co-existence with prior batches):** all four rollups (SBU, Branch, Customer, Staff) reconcile to bank simultaneously, format functions readable

**Section 6 (gates + regression):** G256 passes, G257 passes, Charter §2 still passes

## Files changed

| File | Change |
|---|---|
| `utils/customer_pbt_allocator.py` | **NEW** (~530 LOC, 11 self-tests) — per-customer + per-staff |
| `data/customer_allocation_rules.json` | **NEW** — Rule N1 admin config |
| `scripts/audit.py` | **NEW** `gate_customer_reconciliation` (G256) + `gate_staff_reconciliation` (G257) |
| `scripts/verify_local_state.py` | Extended to 256 checks |
| `tests/integration/test_v10370_customer_staff_reconciliation.py` | **NEW** — 18 tests across 6 sections |
| `docs/Master_Prompt_v4.14.md` | **NEW** — lockstep bump from v4.13 |

**No changes to existing engines.** All prior allocators unchanged. v10.370 adds a new dimension (customer atomic + staff aggregation) without disturbing any prior reconciliation.

## Verified outcome

| Metric | Value |
|---|---|
| **Σ(Customer PBT) - Bank PBT** | **6 KES** (well within KES 100; OpEx exact) |
| **Σ(Staff PBT) - Bank PBT** | **6 KES** (well within KES 100; OpEx exact) |
| Customers in seeded result | **100** (production at Ecobank scale: 700,000) |
| Staff codes in seeded result | **28** (production: hundreds) |
| Allocation rules | 4 (revenue_weighted default, balance_weighted, equal, hybrid) |
| Audit gates | 255 → **257** (G256, G257 lock identities) |
| Charter §2 (G249) | still PASS |
| SBU identity (G254) | still PASS |
| Branch identity (G255) | still PASS |
| Reconciliation diagnostic (G253) | still informational (Engine B refactor → v10.372) |
| Page smoke | 123/123 + 0 static + 14/14 dynamic (preserved) |
| Tests | +18 in v10.370; **185 total across v10.358–v10.370** |
| Verifier | 245 → **256 checks** |
| Master prompt | v4.13 → **v4.14** — lockstep (15 consecutive batches) |
| G162 baseline | 4022 (**64 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **Per-customer is now THE atomic unit.** Every other rollup (SBU, Branch, Staff) becomes Σ over per-customer. This is the architectural insight from Joshua's "drill down to per-customer ultimately" framing. The other engines (compute_pbt_by_sbu, compute_pbt_by_branch) currently still walk accounts.csv directly — for now they're parallel paths that happen to reconcile because they're rolling up the same underlying data. A future cleanup batch could refactor SBU and Branch to consume from per-customer too, making the dependency explicit. Not in scope for v10.370.

2. **Default rule for customer is `revenue_weighted`, not the FTE-weighted of v10.369.** Different domain. Per-branch OpEx follows headcount (FTE drives building space, salaries, utilities). Per-customer OpEx follows revenue generated (more revenue → more attention from RMs and operations → more OpEx absorbed). Both are admin-configurable; tenants can switch.

3. **OpEx reconciles EXACTLY (no tolerance).** Drift absorption on the customer side (largest-revenue customer takes rounding remainder) ensures `Σ(Customer OpEx) == bank.total_opex` exactly. Through staff aggregation, this exactness is preserved (sum identity). PBT still tolerates ±KES 100 because income and impairment have their own per-account Decimal rounding from v10.366 synthesizer.

4. **The staff-role question is intentionally deferred.** `compute_pbt_by_staff` is role-neutral. Joshua's "still thinking" framing on tellers is honored by leaving the data engine simple and pushing role filtering to UI. When the design crystallizes, the UI joins downstream data — no engine change needed.

5. **Service-cost attribution is a real future concern.** When tellers transact on accounts they generate cost (their salary, their time) but don't generate sales revenue. In a sophisticated activity-based costing model, those tellers should absorb a slice of customer OpEx based on transaction volume rather than account ownership. This requires per-transaction staff tagging in CBS (not currently available). When that lands, the path forward is `cost_allocation_rules.json::matrix` mode driving per-transaction allocation. Until then, the current model treats all tagged staff equally as portfolio owners — a simplification that works for the dominant case (BRM/SRO/RO tagging) and over-counts service staff.

6. **The `Unassigned` bucket protects the identity.** Even if some customers have no `rm_code` in customers.csv (data quality issue), they're not silently dropped — they appear in the Unassigned bucket with their PBT contribution intact. Bank total still equals Σ. UI can surface "X customers in Unassigned" as a data quality alert.

7. **Per-customer at production scale (700K customers).** The seeded bank has 100 customers; production would have 700K. The current implementation iterates accounts.csv once (O(accounts)) then iterates customers once (O(customers)). For 700K customers and ~2M accounts, this should run in a few seconds — well within budget. No caching needed yet; if it becomes a bottleneck later, persist per-customer PBT to disk and refresh nightly.

8. **`PBTComponents` is reused for customer, staff, branch, SBU.** Same data class throughout. This is intentional — each level is a P&L in the same structural shape. Easier to compose, test, and serialize. The downside is that some fields (like `cost_of_funds_pct`) are duplicated per bucket. Memory is cheap; coherence is valuable.

9. **Format functions show top N + bottom N for customers** (most profitable AND most loss-making) but only top N for staff. Different framings — customers want to surface both the rainmakers and the unprofitable customers; for staff the focus is typically the top performers.

10. **Co-existence test (`test_v10370_all_four_rollups_reconcile`) catches whole-system regressions.** If a future batch breaks any rollup's reconciliation, this test fails immediately. The test uses KES 200 tolerance (2× the per-rollup tolerance of 100) to allow for compound rounding across rollups.

11. **Self_test grew from 9 to 11 tests** to cover the staff aggregation path (which doesn't exist in the simpler v10.369 allocator). Hand-rolled fixtures pattern continued from v10.364.

12. **Rule N2 held.** v10.370 ships exactly one architectural concern: "per-customer as atomic unit, with staff as derivative aggregation". They're so tightly coupled (staff = Σ customers) that splitting them would be artificial. The single batch covers one purpose.

13. **The v10.364 module-purity lesson held.** `customer_pbt_allocator` imports only `pbt_computation` (legitimate downward) — not `virtual_bank_*`, not `actuals_engine`. Self_test uses hand-rolled CSV fixtures, not seed-and-persist. G128 stays green.

14. **bank_targets.json still lacks per-customer/per-staff targets.** With v10.370 we have per-customer ACTUALS but no per-customer TARGETS. The MD can see "customer X earned KES 1.2M PBT" but not "vs target X.X". v10.371 (multi-level bank_targets schema) closes this — the natural next batch.

15. **rm_profitability.py wasn't refactored.** The original v10.367 architecture review proposed v10.370 = "refactor rm_profitability.py to consume canonical". That assumed per-RM was the goal. Joshua's "drill to per-customer ultimately" reframed the goal — per-customer is now atomic, and per-staff (including RMs) is a thin Σ on top. The existing `rm_profitability.py` (809 LOC) becomes a higher-level consumer that can switch to canonical when needed; it's not blocking and not breaking. Cleanup candidate for a future batch.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10370_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 256 CHECKS PASSED**
5. **See per-customer + per-staff breakdowns:**
   ```
   python -c "
   import tempfile
   from pathlib import Path
   from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
   from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
   from utils.customer_pbt_allocator import (
       compute_pbt_by_customer, compute_pbt_by_staff,
       sum_customer_pbts, sum_staff_pbts,
       format_top_customers, format_staff_breakdown,
   )
   from utils.pbt_computation import compute_pbt_from_cbs
   bank, _ = seed_virtual_bank(config=SeedConfig.small())
   with tempfile.TemporaryDirectory() as td:
       persist_bank_to_cbs(bank, output_dir=Path(td))
       cust_pbts = compute_pbt_by_customer(Path(td))
       staff_pbts = compute_pbt_by_staff(Path(td), customer_pbts=cust_pbts)
       bank_pbt = compute_pbt_from_cbs(Path(td))
       cust_total = sum_customer_pbts(cust_pbts)
       staff_total = sum_staff_pbts(staff_pbts)
       print(format_top_customers(cust_pbts, top_n=5))
       print()
       print(format_staff_breakdown(staff_pbts, top_n=5))
       print()
       print(f'Customer identity: Δ = {float(bank_pbt.pbt - cust_total.pbt):,.0f} KES')
       print(f'Staff identity:    Δ = {float(bank_pbt.pbt - staff_total.pbt):,.0f} KES')
   "
   ```
6. Read `docs\Master_Prompt_v4.14.md` — fifteenth consecutive lockstep batch.
7. (Optional, takes >5min) Audit → expect **257/257 PASS**

## Decisions awaiting your direction (v10.371+)

1. **Multi-level `bank_targets.json` schema** (v10.371) — key shape proposal: `PBT|<level>|<entity>|<year>` where `level ∈ {bank, sbu, branch, staff, customer}`. Example: `PBT|sbu|Retail Banking|2026`, `PBT|branch|BR001|2026`, `PBT|staff|300046|2026`. The existing `PBT|2026` becomes aliased to `PBT|bank|all|2026` for backward compatibility. Approve schema? Or different shape?

2. **Per-target validation rule** — should `Σ(SBU targets) == bank target` be enforced (admin gets an error if SBU targets sum to less/more than bank target)? Or just warned? My recommendation: enforce on save (admin must fix before submitting); allow override with an explicit `_force_unbalanced_targets=true` flag for edge cases.

3. **Role definitions for staff filtering** (eventually, post-v10.372) — which roles are "portfolio-owning" vs "service"? Proposal: `users.json::role ∈ {BRM, SRO, RO, RM, Branch Manager, Regional Head}` → portfolio owners; everything else → service/operations. Tenants can override via a config flag. This isn't blocking v10.371-v10.372, but lands in v10.373.

## v10.371+ roadmap

| Batch | Concern | Closes |
|---|---|---|
| **v10.371** | Multi-level `bank_targets.json` schema | Top-down targets at every level; G253 → CONVERGED |
| **v10.372** | Engine B (`sbu_pnl_rollup`) refactor to consume canonical | Eliminates parallel-engines structural debt; G253 finally locks |
| **v10.373** | Role-aware UI for staff PBT (filter by portfolio-owning vs service) | Resolves teller-vs-RM framing |
| **v10.374+** | UI surfacing of new dimensions in MD dashboard, Finance hub | Visible drill-downs |
| **v10.4XX+** | React executive frontend (Standard #9) | Next major arc |

**Three of five unification batches done. Two architectural batches to go; then UX surfacing.**

Want me to proceed with v10.371 (multi-level bank_targets schema)?
