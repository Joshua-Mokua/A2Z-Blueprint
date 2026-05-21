# A2Z MIS 360 — System State Review

**Version anchor:** v10.373 (May 2026)
**Purpose:** Deep survey of what the system contains, where the profitability-unification pattern would apply next, and the roadmap to make every staff role and module simulatable in the virtual bank.
**Written before any further unification or UI work** to ensure we do not re-build what already exists and that subsequent batches target maximum value per Joshua's directive: "what we have done with profitability unification happens across".

---

## Part 1 — System scale (verified counts)

| Surface | Count |
|---|---:|
| Pages (`pages/[0-9]*.py`) | **123** |
| Utils modules (`utils/*.py`) | **439** |
| Top-level data files (`data/*.json`) | **208** |
| Total LOC (utils + pages) | **383,548** |
| Audit gates | **258** |
| Integration tests across v10.358-v10.372 | **216** |
| Protected data files (schema-validated) | **19** |
| Profitability allocator engines now CANONICAL | 4 (SBU, Branch, Customer, Staff) |
| Legacy profitability engines STILL parallel | 5+ (see Part 3) |

---

## Part 2 — The simulation gap (this is the big one)

Two completely different simulation models coexist:

### Model A — Live action interface (current)
- **Only `utils/teller_actions.py`** exists with this pattern.
- Surface: `fire_teller_deposit(bank, account_no, amount)`, `fire_teller_withdrawal(...)`, `find_first_deposit_account(bank)`.
- **The action mutates the live VirtualBankCore object**, then persists to CBS via `persist_bank_to_cbs`, then Engine A reads the updated CBS and computes new bank PBT.
- This is what Charter §2 (G249) exercises: teller fires deposit → bank PBT recomputes → MD sees the difference. The "Football Team Test" passes.
- **Only the teller role has a live action interface.**

### Model B — Static activity generators (legacy)
- **All other roles** use deterministic-hash generators that produce STATIC BSC scorecard activity:
  - `branch_staff_generator.py`
  - `branch_manager_generator.py`
  - `credit_activity_generator.py`
  - `proposition_activity_generator.py`
  - `specialist_activity_generator.py`
  - `support_function_generator.py`
  - `teller_activity_generator.py` (NB: separate from `teller_actions.py`)
- These pre-compute KPI numbers per period using `_stable_hash(staff_code, period, kpi_id)` and write them to the BSC actuals files.
- **They do not mutate the bank.** They cannot produce live PBT impact. They generate "what activity looked like" rather than "what activity is happening right now".

### Roles that need live action interfaces

To meet Joshua's stated objective — *"run real virtual simulations of every staff role and module"* — every role with measurable bank impact needs an action interface analogous to `teller_actions.py`. Mapping:

| Role | Live actions needed | Today | Gap |
|---|---|---|---|
| **Teller** | Deposit, withdrawal | ✓ (v10.358) | — |
| **CSO / Branch Operations** | Account open, statement, cheque, dispute | ✗ | NEW |
| **BOS / Branch Operations Supervisor** | Approve teller exception, cash mgmt | ✗ | NEW |
| **RM Retail (RM PB / RM BB)** | Onboard customer, sell product, pricing exception | ✗ | NEW |
| **DSO / Direct Sales Officer** | Acquisition, KYC, account funding | ✗ | NEW |
| **RM SME / Corporate** | Credit application, relationship deepening | ✗ | NEW |
| **Branch Credit Manager** | Loan approve/decline, recovery action | ✗ | NEW |
| **Branch Operations Manager** | Branch escalation, exception override | ✗ | NEW |
| **Branch Manager** | Branch-level commitment, RM assignment | ✗ | NEW |
| **Regional Head** | Branch performance review, capital ask | ✗ | NEW |
| **Head of Retail / SME / Corporate** | Strategic pricing, product launch | ✗ | NEW |
| **Director Retail / Commercial Banking** | Capital allocation, hiring | ✗ | NEW |
| **Credit Officer (Head Office)** | Credit policy, NPL provisioning | ✗ | NEW |
| **Treasury Officer** | FTP rate set, FX position, liquidity action | ✗ | NEW |
| **Treasurer (Head)** | ALM decision, funding plan | ✗ | NEW |
| **Risk Officer** | Limit set, breach approval | ✗ | NEW |
| **CRO** | Risk appetite, capital stress | ✗ | NEW |
| **Compliance Officer** | Alert investigation, KYC review | ✗ | NEW |
| **AML Analyst** | SAR file, sanctions check | ✗ | NEW |
| **Internal Auditor** | Issue raise, finding close | ✗ | NEW |
| **Finance** | Reclassification, accrual adjustment | ✗ | NEW |
| **CFO** | Budget approval, financial commitment | ✗ | NEW |
| **MD** | Board commitment, bank-level pricing | ✗ | NEW |
| **CIO / Technology** | Platform incident, capacity decision | ✗ | NEW |
| **HR** | Hire, promote, training assignment | ✗ | NEW |

**That's ~25 roles needing live action interfaces. Today: 1 done.**

The pattern is established: `utils/<role>_actions.py` exporting `fire_<verb>_action(bank, ...)` that mutates the bank, persists, and lets all reconciliation identities recompute.

---

## Part 3 — Parallel engines remaining (the next unification frontier)

We unified bank-level + SBU + Branch + Customer + Staff + targets via v10.368-v10.372. But these legacy modules still walk their own data paths:

### 3.1 Customer profitability — DUAL ENGINES

| File | Purpose | Source data | Status |
|---|---|---|---|
| `utils/customer_pbt_allocator.py` | v10.370 canonical | CBS accounts.csv + customers.csv | NEW |
| `utils/customer_profitability.py` | Pre-v10.370 legacy | customer_intelligence.json | PARALLEL |

The legacy `customer_profitability.py` has its own `save_pnl(customer_id, period, pnl)` / `get_pnl(...)` and assumes external sources for revenue, direct_costs, overhead pool, allocation inputs, FTP. This is **structurally identical** to the Engine A vs Engine B problem we just closed at bank level.

**Recommended unification (v10.375 or later):** add a `cost_source="canonical"` mode to `customer_profitability.get_pnl` that consumes from `compute_pbt_by_customer`. Same pattern as v10.372.

### 3.2 RM profitability — STILL ITS OWN ENGINE

| File | Purpose | Source data | Status |
|---|---|---|---|
| `utils/customer_pbt_allocator.py::compute_pbt_by_staff` | v10.370 canonical (role-neutral) | per-customer atom | NEW |
| `utils/rm_profitability.py` (809 LOC) | Legacy RM portfolio computation | Multiple sources via callbacks | PARALLEL |

The v10.370 acknowledgements flagged this. The legacy module accepts callbacks (`rm_customer_lookup`, `customer_pnl`, `all_rms`) and assembles portfolios. Conceptually it's a higher-level aggregator that could now consume from `compute_pbt_by_staff` for the data.

**Recommended unification (v10.376):** refactor `rm_profitability.get_portfolio(rm_code)` to call `compute_pbt_by_staff()[rm_code]` for the canonical numbers. Preserve the higher-level enrichment (target comparisons, ranking, narratives).

### 3.3 Product profitability — UNVERIFIED

| File | Purpose | Status |
|---|---|---|
| `utils/product_profitability.py` | Per-product P&L | Unsurveyed — may already conform or may be parallel |

**Recommended action:** verify against canonical pattern in a future batch.

### 3.4 Profitability helpers / consumers — VERIFY

These exist as helper modules; need to confirm they consume from canonical:
- `utils/profitability_heatmap.py`
- `utils/profitability_hierarchy.py`
- `utils/profitability_integration.py`
- `utils/profitability_trends.py`

### 3.5 Bank-level rollup entry points in Engine B

`sbu_pnl_rollup.bank_total_pnl` got canonical mode in v10.372. But the other entry points didn't:
- `rollup_by_segment(period, customer_pnl_fn, cost_source)`
- `rollup_by_cbk_sector(...)`
- `rollup_by_tagged_rm(...)`
- `rollup_by_proposition(...)`

Each of these still composes a custom rollup. **Migrating them to canonical** would let SBU drill-down, CBK regulatory reporting, RM cockpit, and propositions all share the same source of truth.

---

## Part 4 — Other modules needing unification (the broader pattern)

The profitability arc surfaced a pattern: **atomic unit + reconciliation identity + canonical engine + audit gate + backward-compat preserved**. Where else does this pattern apply?

### 4.1 Risk

Many parallel risk modules:
- `credit_risk_irb.py`, `credit_risk_scoring.py`, `credit_alt_scoring.py`, `analytics_credit_workbench.py`
- `market_risk.py`, `market_risk_factors.py`, `market_risk_limits.py`, `market_risk_sensitivities.py`, `market_risk_var.py` (5 separate files)
- `liquidity_risk.py`, `liquidity_stress.py`
- `ifrs7_disclosures.py`, `ifrs9_classification.py`
- `compliance_risk_assessment.py`, `kyc_aml_risk.py`, `oprisk_*` modules, `climate_risk.py`
- `capital_adequacy.py`

**The atomic unit:** per-exposure (per-loan, per-position) RWA, expected loss, capital consumption. **The reconciliation identity:** Σ(exposure RWA) == Bank RWA == regulatory capital reported. **The unification frontier here is at least as large as profitability.**

### 4.2 Customer / 360

Parallel customer engines:
- `customer_behavioral_profile.py`
- `customer_lifetime_value.py`
- `customer_needs_analyzer.py`
- `customer_segmentation.py`
- `customer_value_segments.py`
- Plus customer_intelligence.json (3,206 customers) — the legacy customer master
- Plus CBS customers.csv (now canonical from v10.368) — the new canonical
- Plus v10.370 atomic per-customer PBT

**The atomic unit:** per-customer canonical record. **The reconciliation identity:** every consumer (CLV, segmentation, behavioral, profitability) sees the SAME customer master. Today there's drift between customer_intelligence.json (3,206 customers) and CBS customers.csv (100 in seed; would be 700K in production).

### 4.3 Treasury / ALM / FTP

- `treasury_alm.py`, `treasury_agents.py`, `treasury_connectivity.py`, `treasury_dashboard.py`
- `liquidity_risk.py`, `liquidity_stress.py`
- `islamic_treasury.py`, `climate_treasury_limits.py`
- `api_treasury.py`

**The atomic unit:** per-position cash flow at maturity bucket. **The reconciliation identity:** Σ(position cash flow) == bank balance sheet liquidity gap == reported LCR/NSFR.

### 4.4 Bank targets — extended in v10.371 but other "plans" exist

We extended `bank_targets.json` to multi-level. Are there other "plan" files that should also be hierarchical?
- Budget (`pages/budget.py` exists)
- Capital plan
- Strategic initiatives
- BSC targets (cascaded via `cascade_hierarchy.py`)
- Cost allocation rules (already multi-level via cost_allocation_rules.json)

### 4.5 Compliance / CIMS

15+ CIMS modules, multiple compliance modules. Atomic unit likely: per-case investigation. Reconciliation: Σ(open cases by type) == regulatory open cases count.

---

## Part 5 — Strategic roadmap (proposed)

Based on the survey, here is the priority order. **Each batch is one purpose** (Rule N2).

### Phase A — Surface the unification we just shipped (UX visible)

| Batch | Concern | Why first |
|---|---|---|
| **v10.373** (this batch) | System State Review document + this roadmap | Strategic clarity; avoids rebuilding |
| **v10.374** | Role-aware filter for staff PBT (BRM/SRO/RO vs Tellers/CSOs/BOS); first visible UI of v10.370 work | Resolves teller-vs-RM framing Joshua raised |
| **v10.375** | MD dashboard tile: SBU + Branch drill-down using canonical engine | Joshua's One Question becomes drillable |

### Phase B — Close the remaining parallel engines (extend unification pattern)

| Batch | Concern |
|---|---|
| **v10.376** | Refactor `customer_profitability.py` to consume from `customer_pbt_allocator` canonical (Section 3.1) — adds `cost_source="canonical"` parameter, preserves callback API for backward compat |
| **v10.377** | Refactor `rm_profitability.py` to consume from `compute_pbt_by_staff` (Section 3.2) |
| **v10.378** | Refactor remaining `sbu_pnl_rollup` rollup entry points (Section 3.5) — `rollup_by_segment`, `rollup_by_cbk_sector`, `rollup_by_tagged_rm`, `rollup_by_proposition` |
| **v10.379** | Survey + categorize remaining `profitability_*.py` modules (Section 3.4); decide which are consumers and which are parallel engines |

### Phase C — Live action interfaces for every role (the big simulation push)

This is the largest arc. Pattern proven by v10.358 (`teller_actions.py`). Each batch ships one role's action interface plus a Charter §2-style end-to-end test.

| Batch | Role | Live actions |
|---|---|---|
| **v10.380** | CSO / Branch Ops | Account open, statement, cheque, dispute logging |
| **v10.381** | RM Retail (BB / PB) | Onboard customer, sell product, log interaction |
| **v10.382** | RM SME | Credit application initiation, relationship deepening |
| **v10.383** | RM Corporate | Same, with larger ticket sizes |
| **v10.384** | DSO | Acquisition action, KYC submit, account funding |
| **v10.385** | Branch Credit Manager | Loan approve/decline, NPL action, recovery |
| **v10.386** | Branch Operations Manager | Exception override, cash management |
| **v10.387** | Branch Manager | Branch commitment, RM portfolio reassignment |
| **v10.388** | Regional Head | Performance review, capital ask |
| **v10.389** | Head of Retail / SME / Corporate | Pricing decision, product action |
| **v10.390** | Director Retail / Commercial Banking | Capital allocation, hiring approval |
| **v10.391** | Credit Officer (Head Office) | Credit policy, NPL provisioning |
| **v10.392** | Treasury Officer | FTP rate set, FX position, liquidity action |
| **v10.393** | Treasurer (Head) | ALM decision, funding plan |
| **v10.394** | Risk Officer + CRO | Limit set, breach approval, risk appetite |
| **v10.395** | Compliance Officer + AML Analyst | Alert investigation, KYC review, SAR file |
| **v10.396** | Internal Auditor | Issue raise, finding close |
| **v10.397** | Finance + CFO | Reclassification, accrual, budget approval |
| **v10.398** | CIO / Technology | Platform incident, capacity decision |
| **v10.399** | HR | Hire, promote, training assignment |
| **v10.400** | MD | Board commitment, bank-level pricing |

Each batch follows the same pattern:
1. `utils/<role>_actions.py` with `fire_<verb>` functions
2. Each action mutates `VirtualBankCore`, persists to CBS, recomputes PBT
3. Self_test exercises every action against a seeded bank
4. Integration test: do action → check identity still holds → check PBT delta matches expected
5. New audit gate Gxxx: locks the action interface
6. Master prompt sync (lockstep continues)

### Phase D — Apply the unification pattern to other modules

Once roles are simulatable, each module can be unified:

| Batch range | Module |
|---|---|
| **v10.40X** | Risk unification — atomic per-exposure RWA + reconciliation to bank capital |
| **v10.41X** | Customer 360 unification — atomic per-customer master, all consumers reconcile |
| **v10.42X** | Treasury / ALM unification — atomic per-position cash flow + reconciliation to balance sheet |
| **v10.43X** | Compliance / CIMS unification — atomic per-case + reconciliation to regulatory reporting |
| **v10.44X** | HR / Performance unification — atomic per-staff KPI + reconciliation to BSC |

### Phase E — UI surface for everything

After engines are unified and roles are simulatable:

| Batch range | Concern |
|---|---|
| **v10.45X+** | MD dashboard surfaces every dimension across every module |
| **v10.46X+** | React executive frontend (Standard #9) |

---

## Part 6 — Recommended next concrete batch

**v10.374 — Role-aware filter for staff PBT.**

Why this and not jumping ahead to live action interfaces:

1. It's the natural next batch (was the v10.373 roadmap item from before this review).
2. It surfaces the v10.370 unification visibly — partial completion of Phase A.
3. It's small and well-scoped (Rule N2).
4. It establishes the `users.json::role` join pattern that every future role-specific UI will use.
5. It directly resolves Joshua's teller-vs-RM framing.

After v10.374 ships, v10.375 surfaces SBU + Branch drill-down in the MD dashboard. Then Phase B closes the remaining parallel engines.

The big simulation arc (Phase C) starts when Phase A and Phase B are done — by then the canonical engines are fully consolidated and surfaced, so each new live action interface plugs into a stable foundation.

---

## Part 7 — Decisions awaiting Joshua

Before v10.374 (or any subsequent batch), the following decisions would clarify direction:

1. **Roadmap approval**: is this phasing (A → B → C → D → E) the right order? Or should Phase C (simulation) start sooner — perhaps after just v10.374?
2. **Role definitions for portfolio-owning vs service staff**: proposal `{BRM, SRO, RO, RM, Branch Manager, Regional Head}` are portfolio owners; everyone else is service. Confirm or adjust?
3. **Phase C scale**: ~25 roles × one batch each = a large arc. Should we batch some roles together (e.g., all branch-level field staff in one batch) to compress, or keep one-role-per-batch for clarity?
4. **Customer master alignment**: the legacy `customer_intelligence.json` (3,206 customers) and CBS customers.csv (100 in seed / 700K production) are two different customer universes. Should we unify them via a migration, or keep them separate (customer_intelligence as "marketing master", CBS as "transactions master") with a documented mapping?

---

## Part 8 — What this review is NOT proposing

To be explicit about boundaries:

- **Not proposing**: rewriting any of the 439 utils modules wholesale.
- **Not proposing**: deleting any legacy engines. The unification pattern preserves backward compatibility (proxy/matrix modes still work in v10.372) — we add canonical paths, we don't remove old ones.
- **Not proposing**: changing the audit framework, the lockstep discipline, the patterns N1-N8, or the test conventions. All of these are working.
- **Not proposing**: a v11.0 rewrite. The continuous-improvement pattern (one batch at a time, audit-gated, master-prompt-synced) is the right cadence and will simply continue.

The system is healthy. The arc closed in v10.372 demonstrates the unification pattern works. This review identifies where to apply it next, in priority order.
