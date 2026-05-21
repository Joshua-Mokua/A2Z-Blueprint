# CHANGELOG v10.30 — VIRTUAL BANK SIMULATION ARC BATCH 1: FOUNDATION

**Audit:** 124/124 PASS — **113th consecutive clean.**
**Tests:** 623 integration (+18 from v10.29's 605) + 27 self-tests on the new engine.
**Status:** Phase 2 Virtual Bank simulation arc OPEN at batch 1 of 2.

---

## What v10.30 ships

`utils/virtual_bank_core.py` (1175 lines, **Cat B**) — deterministic simulation testbed for the platform's modules. **No regulatory standards activated** — this arc is pure infrastructure (simulation framework lets us test platform modules without needing real FLEXCUBE access).

### Components

| Component | Implementation |
|---|---|
| **Mock FLEXCUBE adapter** | Drop-in API surface matching `utils/flexcube_adapter`: `fetch_account_balance`, `fetch_customer`, `fetch_loan_status`, `fetch_branch_metrics`, `fetch_rm_portfolio`. Every response carries `sim_seed` + `sim_day_offset` for reproducibility tracing |
| **Banking entity simulator** | `VirtualCustomer` (5-segment enum: RETAIL/SME/CORPORATE/HNW/PRIVATE_BANKING) × `VirtualAccount` (5 types: SAVINGS/CURRENT/FIXED_DEPOSIT/LOAN/OVERDRAFT) × `VirtualLoan` (10-state lifecycle) × `VirtualBranch` × `VirtualTransaction` |
| **Loan state machine** | 10 states aligned with CBK PG/04 risk classification: APPLICATION → APPROVED → DISBURSED → PERFORMING → DELINQUENT_30 → DELINQUENT_60 → DELINQUENT_90 → NON_PERFORMING → WRITTEN_OFF → CLOSED. `ALLOWED_LOAN_TRANSITIONS` graph enforces governance — cannot skip stages |
| **Deterministic seeding** | `derive_seed(base_seed, namespace, discriminator)` — SHA-256 derivation. `deterministic_pseudo_random` — LCG with explicit Numerical Recipes parameters. Same inputs → same outputs always, across runs and platforms |
| **Time controller** | `tick(days=N)` advances simulation time; refuses negative ticks. `current_date()` returns Python date for the simulation moment |
| **Day-end batch** | Simple-interest accrual on SAVINGS + FIXED_DEPOSIT accounts (Decimal arithmetic throughout — no float on money). Loan aging via `days_past_due` recompute → `loan_status_from_dpd` → state-machine-validated transition. Idempotent: same-day reruns skip already-posted INT- prefixed transactions |

## Key design decisions

**Determinism is the first-class invariant.** The tests verify two banks with the same seed produce the same `board_summary` after the same operations. This is what makes the simulator useful as a testbed — flaky tests are eliminated by construction.

**Cat B classification, not Cat A.** This module does NOT affect production capital, credit decisions, or regulatory reporting. Failures here would manifest as broken tests, not broken bank operations. Risk profile differs from v10.6-v10.29 regulatory work.

**Drop-in compatibility with `utils/flexcube_adapter`.** Same fetcher signatures, same response shape (with `MockResponse` wrapper carrying simulation metadata). Platform modules that today call FLEXCUBE can test against the simulator with a single import swap.

**No real network, file system, or DB calls.** The simulator is pure in-memory Python. This makes tests fast (sub-second) and isolated (no shared state across test runs).

**No standards activation.** Unlike v10.6-v10.29 arcs, this 2-batch arc activates no regulatory standards from the registry — it's pure operational utility. The standards remain Cat A regulatory work; the simulator is Cat B test infrastructure.

**Decimal throughout for money.** No float arithmetic. Interest accrual uses `Decimal("3.65") / Decimal("100") / Decimal("365")` to avoid floating-point drift on small daily amounts.

## Honesty rules enforced

**Rule 1** — every `MockResponse` payload carries `sim_seed` + `sim_day_offset` for traceability. Unknown account/customer/loan/branch surfaces explicit `{"error": "X_not_found"}` rather than silent default. Loan transitions surface explicit error message identifying allowed transitions.

**Rule 7** — market-data fetcher (CBR, KESONIA, FX rates) is callable hook (designed in for v10.31's scenario injection). Without wiring, simulator uses scenario-defined defaults rather than fabricating live market data.

## Tests

**27 self-tests** covering: seed determinism (3) + loan state machine (3) + day-end interest (2) + DPD computation (3) + bank entity registration (2) + time control (2) + transaction posting (1) + day-end interest accrual (1) + day-end idempotency (1) + day-end loan aging (1) + mock FLEXCUBE adapter (5) + invalid loan transition (1) + board summary (1) + cross-bank determinism (1).

**18 integration tests** in `tests/integration/test_v10_30_virtual_bank_core.py` covering imports + public symbols + determinism + loan lifecycle + day-end + mock adapter + coexistence with v10.23-v10.29 stack.

## Engine Hub

Tier 13 added to `pages/7_admin.py` — surfaces `virtual_bank_core` engine alongside the 12 existing tiers.

## Acknowledgements

Different shape from regulatory arcs. The 5/6-batch + closure pattern still applies (foundation → simulator/scenarios + closure), but compressed and oriented toward operational utility rather than regulatory standard activation.

## What v10.31 ships next

`utils/virtual_bank_simulator.py` (~900-1100 lines):
- `DailyOpsSimulator` — generates deterministic daily transaction streams (deposits, withdrawals, transfers) seeded by `derive_seed`
- `ScenarioInjector` — injects scenarios into the simulation: stress events (rate shocks, deposit runs), fraud patterns (velocity attacks, structuring), drift events (population shift), AML triggers
- `SimulationRun` lifecycle (CONFIGURED → RUNNING → COMPLETED) with explicit state machine
- `SimulationReport` with deterministic metrics
- **G125 audit gate** locking the closure set
- 4 drift tests verifying gate behavior
- Closing CHANGELOG_v10.31.md with 2-batch retrospective

## Honest closing notes for v10.30

1. **Lightweight by design — not a full core banking system simulation.** The simulator covers customer/account/loan/branch/transaction abstractions but doesn't model GL, treasury operations, FX revaluation, or interbank settlement. Sufficient for testing platform modules that depend on FLEXCUBE-style fetchers; not sufficient for regulatory stress-testing the bank's actual capital position.

2. **Day-end batch is simple-interest only.** Real banks use compound interest with mid-month rate changes, fee waivers, taxation rules, etc. The simulator covers the structural shape; production wires actual interest engines.

3. **No persistence.** Each `VirtualBankCore` instance is in-memory. Cannot resume a simulation across process restarts. By design — simulation determinism comes from seeds, not persisted state.

4. **No actual FLEXCUBE integration tests.** This arc lets the platform's modules test against the mock; v10.31 will exercise modules end-to-end against a populated simulation. Real FLEXCUBE integration testing remains separate per-deployment work.

5. **The simulator can't replace UAT against actual customer data.** It's a unit-test enablement layer, not a substitute for production validation.

113 consecutive clean batches. Virtual Bank simulation foundation in place. v10.31 next opens daily ops simulator + scenario injection + G125 closure.
