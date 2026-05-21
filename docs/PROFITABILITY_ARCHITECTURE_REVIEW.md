# Profitability Architecture Review

**Version:** v10.367 (May 2026)
**Status:** Living document — will be revised as the unification arc progresses
**Audience:** Joshua + future Claude sessions reading TRANSITION_BRIEF
**Purpose:** Map the current state, surface the overlaps, propose the unification

---

## TL;DR

A2Z currently has **two parallel profitability engines** that produce
different bank PBTs from different starting points, and a **third** legacy
formula used in per-branch rollups. They don't reconcile.

This document maps the current state, identifies the reconciliation
identity that *should* hold (`∑(SBU) = ∑(Branch) = ∑(RM) = Bank PBT`),
and proposes a five-batch unification arc (v10.368-v10.372).

v10.367 itself ships only the **measurement infrastructure**:
`utils/profitability_reconciliation.py` runs both engines side-by-side
and reports the delta. G253 monitors the metric (informational only).
Once v10.370 ships the unified foundation, G253 ratchets to require
ΔPBT < 5%.

---

## Current state — the four engines

### Engine A — `utils/pbt_computation.py` (v10.364)

The newest engine. CBS-driven, bank-level only.

| Property | Value |
|---|---|
| Data source | `cbs_data/accounts.csv` + `data/opex_data.json::bank` |
| Time horizon | YTD (synthesized accruals from v10.366) |
| Output | Bank-level only (no drill-down) |
| Used by | `compute_bank_aggregates` → MD's BSC, `bank_targets.json::PBT\|2026` reconciliation |
| Locked by | G250 |

Computes: `PBT = (NII + Non-Interest Income) - Total OpEx - Impairment`
where NII = Interest Income (from accounts.csv) - Interest Expense (deposits × cost_of_funds_pct).

**Strength:** Direct from operational data. Matches what FLEXCUBE would report.
**Limitation:** No drill-down. Single OpEx bucket. Can't show "Retail PBT" or "Branch_001 PBT".

### Engine B — `utils/sbu_pnl_rollup.py` (v10.338)

The older engine. Customer-driven, full drill-down.

| Property | Value |
|---|---|
| Data source | `data/customer_intelligence.json` + `customer_intelligence_business.json` + `cost_allocation_rules.json` |
| Time horizon | Quarterly |
| Output | Segment / CBK Sector / Tagged RM / Proposition drill-downs |
| Used by | `utils.finance_hub_render` → Finance hub UI |
| Reconciles | `reconcile_to_bank()` — segment sums must = bank total (within KES 100 tolerance) |

Computes: walks each customer, accumulates revenue + direct cost + indirect cost. In **matrix mode**, indirect cost comes from 10 driver-based rules in `cost_allocation_rules.json`. In **proxy mode**, per-customer proxy estimates.

**Strength:** Drills to segment/sector/RM/proposition. Has proper cost allocation. Has Rule 6 (propositions overlap → excluded from reconciliation). Already has its own reconciliation method.

**Limitation:** Revenue is *proxy-derived* (CLV for individuals, turnover × NIM for businesses), not from accounts.csv. So it doesn't reflect actual interest/fee income on the books.

### Engine C — `utils/actuals_engine.py::aggregate_cbs_by_branch`

Legacy per-branch PBT. The naive formula.

| Property | Value |
|---|---|
| Data source | `cbs_data/accounts.csv` |
| Time horizon | Whatever the CBS represents |
| Formula | `branch_int + branch_fee - branch_loans × 0.02` |
| Output | Per-branch P&L |
| Used by | Branch ranking pages |
| Reconciles to bank? | No — uses 2% loan-OpEx proxy, no impairment, ignores deposits |

**The same naive formula that v10.364 replaced at bank level**, but still here at branch level because branch-level OpEx allocation needs a separate engine.

### Engine D — `utils/customer_profitability.py`

Customer 360 P&L (953 lines).

| Property | Value |
|---|---|
| Data source | Per-customer record + buckets |
| Output | One customer's full P&L (revenue, direct cost, indirect cost, PBT) |
| Used by | Customer 360 page |
| Relationship to other engines | Engine B *calls* per-customer P&L functions that resemble this (via `customer_pnl_fn` parameter) |

Engine D is genuinely needed (per-customer drill-down is a core feature), but it should ultimately be the *source* that Engine B aggregates from, not an independent computation.

---

## What `opex_data.json::by_sbu` already gives us (and we're not using)

```
Retail Banking      : PBT 1.8B  Income 5.2B  OpEx 3.1B  Staff 680
Commercial Banking  : PBT 1.9B  Income 4.1B  OpEx 2.0B  Staff 95
Corporate Banking   : PBT 1.2B  Income 2.3B  OpEx 0.9B  Staff 32
Treasury            : PBT 0.6B  Income 1.1B  OpEx 0.4B  Staff 8
Digital / Agency    : PBT -0.2B Income 0.6B  OpEx 0.8B  Staff 45
─────────────────────────────────────────────────────────────
Σ SBU              : PBT 5.3B
Bank-level PBT     : PBT 5.4B  (from opex_data.json::bank.pbt_kes_b)
```

**The SBU breakdown already reconciles in the config file** (5.3B ≈ 5.4B, rounding). But neither Engine A nor Engine B reads this for the rollup. Engine A reads only `bank.total_opex_kes_b` (a single bucket). Engine B doesn't know `opex_data.json` exists.

This is a fix waiting to happen.

---

## The reconciliation identity that should hold

```
                    Bank PBT (canonical)
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
    Σ(SBU PBT)      Σ(Branch PBT)     Σ(RM PBT)
                          ║
                  These three sums all equal Bank PBT.
                  Different lenses on the same total.

    Propositions cut across SBUs/Branches/RMs — they overlap,
    so Σ(Proposition) ≠ Bank PBT. This is correct (Rule 6).
    Propositions are informational, not additive.
```

### Where rollup boundaries must hold

| Cut | Σ should = Bank? | Why |
|---|---|---|
| Segment (SBU) | Yes | Every customer belongs to exactly one |
| Branch | Yes | Every account belongs to exactly one |
| RM | Yes | Every customer/account has exactly one (or unassigned bucket) |
| CBK Sector | Yes | Every business belongs to exactly one |
| Proposition | **No** | Customers can be in multiple propositions (overlap) |
| Customer | Yes | Customer is the atomic unit |

This identity is what v10.368-v10.372 must establish.

---

## The unification arc — five batches

### v10.368 — Align data sources

**Problem:** Engine A reads CBS accounts.csv (100 customers in small seed); Engine B reads customer_intelligence.json (3,206 customers). They're seeing different banks.

**Solution:** Make Engine B's customer iteration optionally walk a CBS-derived customer list when CBS data is available. In dev with seeded bank: 100 customers visible to both. In production with FLEXCUBE: same FLEXCUBE customers visible to both.

**Deliverable:** `sbu_pnl_rollup.bank_total_pnl(customer_source='cbs')` mode that reads accounts.csv → customer list → calls `customer_pnl_fn` per CIF. Existing `customer_source='intelligence'` (default) preserved for backward compat.

**G253 ratchets:** ΔRevenue should drop (same customer base). Still informational.

### v10.369 — Add SBU dimension to Engine A

**Problem:** Engine A doesn't know about SBUs. Engine B does but uses proxy revenue.

**Solution:** Extend `compute_pbt_from_cbs` to take an optional `by_sbu=True` flag. When set, walks accounts.csv but groups accounts by their owner's segment (looked up via customer record), and uses `opex_data.json::by_sbu` for per-SBU OpEx allocation.

**Deliverable:** `compute_pbt_from_cbs(cbs_dir, by_sbu=True) → Dict[str, PBTComponents]` returning {Retail: PBTComponents, Commercial: PBTComponents, ...}. Bank PBT = sum.

**G254 (new):** Σ(SBU PBT) == Bank PBT within KES 100 tolerance.

### v10.370 — Per-branch allocation engine

**Problem:** Engine C's naive `int + fee - loans × 0.02` formula doesn't reconcile.

**Solution:** New `utils/branch_pbt_allocator.py`. Reads bank-level OpEx from opex_data.json and allocates to branches by a configurable driver (FTE-weighted from staff_register, revenue-weighted from accounts.csv, or hybrid). The driver choice is admin-configurable (Rule N1) in new `data/branch_allocation_rules.json`.

**Deliverable:** `compute_pbt_by_branch(cbs_dir, allocation_rule='fte_weighted') → Dict[str, PBTComponents]` returning per-branch P&L. Replaces Engine C in `aggregate_cbs_by_branch`.

**G255 (new):** Σ(Branch PBT) == Bank PBT within KES 100 tolerance.
**G253 ratchets:** Now requires ΔPBT < 5% between Engine A and Engine B.

### v10.371 — Per-RM canonical refactor

**Problem:** `rm_profitability.py` (809 lines) has its own P&L methodology that may not match the canonical.

**Solution:** Refactor `rm_profitability.py` to consume from a new canonical function — either `compute_pbt_by_rm` (CBS-driven) or `sbu_pnl_rollup.rollup_by_tagged_rm` (customer-driven) — and verify they agree.

**G256 (new):** Σ(RM PBT) == Bank PBT within tolerance.

### v10.372 — Extend bank_targets.json with multi-level cuts

**Problem:** `bank_targets.json` only has bank-level targets (150 keys = 75 KPIs × 2 years, all bank-level). So top-down targets don't exist for SBUs, branches, or RMs — making the reconciliation one-sided (we can compute bottom-up actuals, but there's no top-down target to reconcile against).

**Solution:** Extend the JSON schema to allow `PBT|<level>|<entity>|<year>` keys. E.g., `PBT|SBU|Retail Banking|2026`, `PBT|Branch|001|2026`, `PBT|RM|RM_ECO_0042|2026`. Reconciliation check: Σ(child targets) == parent target.

**G253 ratchets:** Now requires CONVERGED status (ΔPBT < 1%).

---

## Tradeoffs and design questions for Joshua

### Q1: Which engine is canonical?

- **Engine A (CBS-driven):** matches what FLEXCUBE will eventually provide. Operational truth.
- **Engine B (customer-driven):** richer (drill-downs already wired). Management accounting truth.

**Recommendation:** Engine A is canonical at the bank level (it's what the MD's BSC reads + what `bank_targets.json` compares against). Engine B becomes a dimension cut — `Σ(SBU via A's by_sbu mode) = A's bank total`. Engine B's customer-driven mode is preserved as an alternative lens (for matrix-allocation analyses) but not the source of truth.

### Q2: How to handle the proxy-vs-actual revenue gap?

Engine B uses proxy revenue (CLV-derived). Once v10.368 aligns it to CBS-derived revenue, the proxy mode becomes lossy. **Decision needed:** preserve proxy mode for legacy compatibility, or sunset it?

**Recommendation:** Sunset over two batches. v10.368 makes CBS mode the default; v10.371 removes the proxy fallback. Document the removal in v10.371's CHANGELOG.

### Q3: Allocation driver for v10.370 per-branch?

Three options:
- **FTE-weighted** (staff count per branch): premise = OpEx follows headcount. Common in retail banking.
- **Revenue-weighted** (each branch's contribution to total revenue): premise = OpEx follows revenue. Aligns with "profit-center" thinking.
- **Hybrid 50/50:** half-and-half.

**Recommendation:** Make it admin-configurable in `data/branch_allocation_rules.json`. Default: FTE-weighted (matches `cost_allocation_rules.json::RULE_001` pattern). Admins can switch.

### Q4: Should propositions be visible to the MD?

Propositions cut across the canonical hierarchy. They're useful for portfolio analysis ("Tujenge Pamoja proposition is profitable in Commercial but loss-making in Retail") but cannot reconcile to bank total.

**Recommendation:** Yes — visible to MD but explicitly labeled "informational, doesn't sum to bank". This is what Engine B's Rule 6 already does. Preserve.

---

## What v10.367 ships (this batch)

| File | Purpose |
|---|---|
| `docs/PROFITABILITY_ARCHITECTURE_REVIEW.md` | This document |
| `utils/profitability_reconciliation.py` | Diagnostic module — runs both engines, reports delta |
| `scripts/audit.py` | New `gate_profitability_reconciliation` (G253) |
| `tests/integration/test_v10367_profitability_reconciliation.py` | Tests |

**No engine changes.** Engines A, B, C, D are untouched. v10.367 is pure measurement.

The diagnostic answers: *"Where do the engines disagree, and why?"*
The architecture review answers: *"What should the unified shape be?"*

Once Joshua approves the unification arc, v10.368 ships the first structural alignment.

---

## Open data-schema questions to resolve before v10.372

1. **`bank_targets.json` key shape:** Today: `PBT|2026`. Proposed: `PBT|<level>|<entity>|<year>` where level ∈ {bank, sbu, branch, rm}. Migration: keep `PBT|2026` as `PBT|bank|all|2026` and treat the legacy form as an alias. Approve?
2. **Where to store per-SBU target buffers:** today `bank_targets.json::PBT|2026.buffer_pct=0`. Per-SBU buffers may differ (e.g., Retail target 1.8B ±5%, Commercial 1.9B ±3%). Approve schema extension?
3. **Strategic initiative attribution:** Initiatives currently attach to KPIs at bank level. With SBU-level KPIs, do initiatives attach to bank-level or SBU-level KPIs? Both? **Decision needed.**

---

## Why this matters for Charter §2 / the One Question

Charter §2 says the MD sees teller actions in real-time. v10.363 proved that for **Deposit Growth**. But the MD's One Question — "Is the bank on track to achieve its strategic goals?" — depends on **profitability**, not just deposits. Without engine reconciliation:

- The MD asks "Is Retail Banking on track?" → No reliable answer (Engine A doesn't know SBUs; Engine B's revenue is proxy-derived)
- The MD asks "Is Branch_001 profitable?" → No reliable answer (Engine C uses naive formula)
- The MD asks "Which RM is over-target?" → No reliable answer (RM PBT methodology unverified)

The unification arc makes these answerable. The MD's One Question is met when v10.372 ships and G253 / G254 / G255 / G256 all pass with CONVERGED status.

---

**Decision needed from Joshua:** approve the unification ordering (v10.368 → v10.372), or propose a different sequence. Q1-Q4 above also need direction.

The diagnostic is now shipping (v10.367). Direction on the rest of the arc proceeds the next batch.
