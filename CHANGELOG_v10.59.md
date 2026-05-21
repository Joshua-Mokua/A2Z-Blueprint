# CHANGELOG v10.59 — finance arc OPENS · ENH-249 Continuous Close Orchestration

**Status:** **THIRTEENTH ARC OPENED** on the platform — finance arc opens with 1/10 standards active.
**Audit:** 134/134 PASS · **G128:** STABLE (324 modules · 825 imports · 3 HARD baseline)
**Active standards:** 127 → **128** / 260 · **Scenario library:** 86 → **90** (4 FCO-* added)

## Why this arc, why now

With the revenue_assurance arc closed at v10.58, the registry's earliest remaining slipped subcategory is `finance` — 10 standards (ENH-249..ENH-258) all flagged at v10.42+ deferred batch. ENH-249 leads the arc: continuous close orchestration. Subsequent standards build on it (intercompany matching at ENH-250, group consolidation at ENH-251, CBK regulatory reporting at ENH-252, predictive analytics at ENH-253, CFO dashboard at ENH-254, statement generator at ENH-255, tax compliance at ENH-256, multi-entity/multi-currency at ENH-257, finance audit & compliance at ENH-258).

Each subsequent finance standard composes against ENH-249's `GLEntry` + `CloseAccount` + `CloseTask` dataclasses where applicable — same severity vocabulary discipline that worked across the revenue_assurance arc.

## What this batch does

Diagnostic close-readiness orchestrator. Targets <3-day close per Gartner finance research; does NOT itself close the period. Surfaces what *would need* to be done — recurring accruals not yet booked, prepayments due for amortization, intercompany entries with no offsetting side, uncleared suspense balances, transactions posted in the wrong period.

## New module

- `utils/finance_close_orchestrator.py` (~870 lines · 20 self-tests · all PASS first run). Pure stdlib (`Decimal` + frozen dataclasses + enums). Single public engine `FinanceCloseOrchestrator` with `detect_missing_recurring_accruals`, `detect_prepayment_amortization_due`, `detect_intercompany_pending`, `detect_suspense_balances`, `detect_cutoff_timing`, plus `generate_close_report` orchestrator.

## Architecture — five detection capabilities

### 1. MISSING_RECURRING_ACCRUAL
`RecurringAccrualSchedule` defines an expected recurring accrual (account_code, periodic_amount_kes, frequency, contra_account_code, optional effective_from/to_period bounds). For each schedule active in the target period, the engine checks whether at least one matching `GLEntry` (linked by `schedule_id`) was posted. Missing → recommends `Dr account_code / Cr contra_account_code` at periodic amount. Quarterly schedules only fire in months 3/6/9/12; annual in month 12.

### 2. PREPAYMENT_AMORTIZATION_DUE
`PrepaymentSchedule` with start/end period bounds and per-period amortization amount. Missing posting for the period → recommends `Dr expense_account_code / Cr prepaid_account_code`. Periods outside the [start, end] window are silently skipped.

### 3. INTERCOMPANY_PENDING
For accounts flagged `is_intercompany=True`, the engine pairs entries by `(reference, period)`. If the Dr-side total ≠ Cr-side total for that reference, the side that's unmatched is flagged. Both-sides-equal aggregations are silently skipped — the engine doesn't double-flag balanced IC entries. Counterparty entity ID surfaced when present, "unknown" otherwise.

### 4. SUSPENSE_BALANCE
For accounts flagged `is_suspense=True`, computes net balance through period end. Non-zero → CRITICAL severity (blocks close certification). Zero net (Dr 250k offset by Cr 250k = 0) silently skipped. Period filtering: only entries with `period ≤ target_period` count toward the balance.

### 5. CUTOFF_TIMING
Caller supplies `reference_dates` dict mapping `entry_id → reference_date` (the underlying invoice/receipt date — `GLEntry` only carries posting date). Default 7-day threshold for "significantly outside the period window." `>30-day lag` promotes severity from MEDIUM to HIGH. Engine flags timing — humans decide whether to reverse and repost.

## Engine API surface

```python
class FinanceCloseOrchestrator:
    DEFAULT_TARGET_CLOSE_DAYS: int = 3              # Gartner default
    DEFAULT_CUTOFF_LAG_DAYS_THRESHOLD: int = 7

    def detect_missing_recurring_accruals(...) -> Tuple[CloseTask, ...]
    def detect_prepayment_amortization_due(...) -> Tuple[CloseTask, ...]
    def detect_intercompany_pending(...) -> Tuple[CloseTask, ...]
    def detect_suspense_balances(...) -> Tuple[CloseTask, ...]
    def detect_cutoff_timing(...) -> Tuple[CloseTask, ...]
    def generate_close_report(...) -> CloseReadinessReport
```

`generate_close_report` runs all five capabilities and returns a unified `CloseReadinessReport` with task aggregates by type + severity, ready_for_review_count, blocked_count, and framework refs.

## Validation envelope

Construction-time `__post_init__` checks across the input dataclasses:

- `CloseAccount` rejects empty `account_code` and empty `account_name`.
- `GLEntry` enforces **Dr XOR Cr** (not both > 0, neither both = 0); rejects negative amounts.
- `RecurringAccrualSchedule` rejects non-positive `periodic_amount_kes`.
- `PrepaymentSchedule` rejects non-positive amounts and `end_period < start_period`.

## Rule 1 / Rule 7 alignment

- **8 frozen dataclasses**: `CloseAccount`, `GLEntry`, `RecurringAccrualSchedule`, `PrepaymentSchedule`, `CloseTask`, `CloseReadinessReport`, plus the 5 enum types.
- Every `CloseTask` surfaces: `task_id`, `task_type`, `severity`, `status`, `period`, `account_code`, `recommended_debit_kes`, `recommended_credit_kes`, `contra_account_code`, `description`, `related_ids`, `framework_refs`. Operators have everything needed to action or dismiss.
- Engine is **diagnostic only** (Rule 7):
  - never posts journals (recommends; humans approve and post)
  - never closes the period
  - never auto-clears suspense
  - never reverses entries
  - never mutates GL records (frozen contract enforces this)
- `_test_engine_does_not_mutate_inputs` explicitly verifies the read-only contract.

## Standards registry

- **ENH-249** activated: `status: planned → active`,
  `implementation_batch: v10.42+ → v10.59`,
  `affected_engines: ("finance_close", "consolidation") →
  ("finance_close_orchestrator",)`,
  `source: continuation_doc → research_addition`.
  Description rewritten with the full 5-capability detection taxonomy, severity ladder rationale (CRITICAL for suspense, HIGH for accruals/prepayments/IC, MEDIUM/HIGH for timing based on lag magnitude), validation envelope, and Rule 1/7 contracts.
- Registry self-test PASS · total 260 · active **127 → 128**.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY`:

- **FCO-01 Missing rent accrual** — monthly rent schedule defined, no `GLEntry` for the period → HIGH severity `MISSING_RECURRING_ACCRUAL` task with Dr 500k / Cr 2100 recommendation. Both account codes surfaced for Rule 1. 4 assertions.
- **FCO-02 Suspense CRITICAL** — Dr 250k + Cr 100k = Dr 150k net at period close → `SUSPENSE_BALANCE` task with CRITICAL severity. Net balance value present in description for operator inspection. 3 assertions.
- **FCO-03 Intercompany pending** — parent posted Dr IC-1500 750k vs SUBA but no offsetting Cr on SUBA's books → `INTERCOMPANY_PENDING` task; counterparty SUBA in description; source entry in `related_ids`. 4 assertions.
- **FCO-04 generate_close_report orchestrator** — combined scenario producing 3 distinct task types (missing accrual + prepayment due + suspense); CRITICAL severity from suspense; `target_close_days=3` (Gartner default); framework refs cite ENH-249 + Rule 7 diagnostic-only stance. 4 assertions.

End-to-end runner: FCO-01..FCO-04 all PASS · **15/15 assertions**.
Scenario library 86 → **90**.

## Self-tests

`python3 -m utils.finance_close_orchestrator` → ✓ **20/20** tests covering: validation envelope (6 dataclass `__post_init__` checks including Dr-XOR-Cr), each detection capability with positive + negative cases, quarterly month-of-quarter logic, prepayment outside-window skip, IC pairing logic (paired vs unpaired), suspense zero-balance skip, cutoff threshold logic, `generate_close_report` orchestration, full Rule 1 provenance, immutability contract.

All upstream modules pass with **no regression**:
- revenue_validation 19/19 · revenue_anomaly_patterns 21/21
- revenue_orchestrator 23/23 · partner_supplier_recon 20/20
- revenue_dashboard_metrics 18/18 · continuous_billing_verification 17/17
- commission_assurance 20/20 · regulatory_revenue_reporting 15/15
- finance_close_orchestrator 20/20 · scenario_simulator 18/18
- standards_registry ✓ (total 260)

**173/173 total self-tests across the active engine surface.**

## Gate verification

- `python3 scripts/audit.py` → **Score: 134/134 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings match baseline exactly** (324 modules · 825 imports · 64 findings · HARD=3). Module +1 (finance_close_orchestrator), imports +1.

## Lean+Compact protocol — applied (v10.46 amended)

- 1 ENH per batch (ENH-249) ✅
- ~870 line module
- Engine Hub Tier addition DEFERRED to arc closure (v10.68) ✅
- Master Prompt update DEFERRED to arc closure ✅
- UI integration DEFERRED to arc closure ✅
- Audit + G128 + scenario library extension SHIPPED ✅
- Per Rule 1 every CloseTask surfaces full provenance ✅
- Per Rule 7 engine diagnostic only — verified by mutation test ✅

## Files changed

- **NEW** `utils/finance_close_orchestrator.py` (~870 lines, 20 self-tests)
- **MOD** `utils/standards_registry.py` (ENH-249 activated, ~50 line description rewrite + threshold_unit fix)
- **MOD** `utils/scenario_simulator.py` (+4 FCO-* scenarios + library extension)
- **NEW** `CHANGELOG_v10.59.md`

## Honest scope notes

1. **No actual journal posting.** Engine produces `CloseTask` recommendations with Dr/Cr accounts and amounts. Posting is the operator's responsibility; the closure cockpit (v10.68) will show the recommendations and let operators approve to a downstream posting interface — but the engine itself never posts.

2. **No FX revaluation.** Multi-currency close is ENH-257's territory. ENH-249's `GLEntry.debit_kes` / `credit_kes` fields assume the GL is already in functional currency. Production deployments with foreign-currency operations need FX handling upstream; this engine doesn't touch translation.

3. **IC pairing requires shared reference.** The engine pairs IC entries by `(reference, period)` — if entries don't carry a shared reference field, IC matching falls through silently. ENH-250 will introduce richer IC matching with fuzzy reference resolution; for now, ENH-249 only flags the obvious cases where reference is populated but unbalanced.

4. **Cutoff timing depends on caller-supplied reference dates.** The `GLEntry` schema doesn't carry the underlying invoice/receipt date — the engine only knows the posting date. Caller supplies `reference_dates: Dict[entry_id, date]`. Without that input, cutoff detection is skipped silently. This is honest about the data dependency rather than fabricating reference dates.

5. **No accrual reversal next period.** Production accrual workflows post the accrual in period N and auto-reverse in period N+1 (so the actual invoice in N+1 doesn't double-count). ENH-249 only recommends the period-N accrual; the reversal lifecycle is out of scope.

6. **Period strings, not dates.** The engine uses `"YYYY-MM"` strings for periods rather than `date` objects. Cheap and works for monthly/quarterly/annual; doesn't generalise to non-calendar fiscal years (e.g., a fiscal year ending March 31). Production deployments with non-calendar fiscal years would need a thin period-mapping layer above this engine.

## finance arc state

| Standard | Name | Status | Batch |
| --- | --- | --- | --- |
| **ENH-249** | **Continuous Close Orchestration Engine** | **active** | **v10.59** |
| ENH-250 | Intercompany Matching & Elimination | planned | v10.60 |
| ENH-251 | Group Consolidation Engine | planned | v10.61 |
| ENH-252 | CBK Regulatory Reporting Automation (Enhanced) | planned | v10.62 |
| ENH-253 | Predictive Financial Analytics | planned | v10.63 |
| ENH-254 | Finance Intelligence Dashboard (CFO View) | planned | v10.64 (or split-implementation) |
| ENH-255 | Financial Statement Generator | planned | v10.65 |
| ENH-256 | Tax Compliance & Reporting | planned | v10.66 |
| ENH-257 | Multi-Entity & Multi-Currency Accounting | planned | v10.67 |
| ENH-258 | Finance Audit & Compliance | planned | v10.67+ |
| **closure** | **G135 + G136 + Tier 27 + cockpit (pages/96)** | **planned** | **v10.68** |

## Next batch

**v10.60 — ENH-250 Intercompany Matching & Elimination.** Builds on ENH-249's IC pending detection by adding a true matching engine: fuzzy reference resolution, multi-leg IC chains (parent → sub → sub), elimination journal recommendations. Per Rule 7, recommendations only — the engine never posts elimination journals. Composes with `CloseAccount.is_intercompany` + `GLEntry.counterparty_entity_id` from ENH-249.

**141 consecutive clean batches.** 12 closed arcs hold; **finance arc opens at 1/10**.
