# CHANGELOG v10.173 — ENH-225 Legal Spend Management

Fourth Legal arc engine. Greenfield. Natural complement to ENH-224 (counsel portal feeds approved billings; spend engine accrues against budgets).

**Audit:** `Score: 153/153 gates = 100.0% — PASS`. Active 191→192; G142 floor 89→90. Tests 28/28 pass.

## Engine
- `utils/legal_spend_management.py` ~470 LOC. 4 enums (BudgetStatus 2, VarianceState 4, SpendOrigin 4, TransitionOutcome 5). 3 frozen dataclasses (SpendRecord, Budget, RateCard).
- Budget lifecycle ACTIVE→CLOSED with reason required for closure
- VarianceState computed dynamically: ON_TRACK ≤80%, WARNING 80-95%, AT_LIMIT 95-100%, EXCEEDED >100%
- `record_spend()` rejects currency-mismatched spend against an active budget for the same matter (REJECTED_CURRENCY_MISMATCH)
- `matters_at_or_over_limit()` surfaces breach watch list (AT_LIMIT + EXCEEDED states)
- Rate cards stored per firm × timekeeper_role × currency
- Decoupled from outside_counsel_portal — orchestration layer wires APPROVED billings into spend records via `record_spend(origin=EXTERNAL_BILLING, source_ref=submission_id)`

## Honest deferrals — 3 surfaces
- REAL_TIME_AP_RECONCILIATION DEFERRED — accrual ledger ships; FLEXCUBE GL reconciliation operator-side
- RATE_NEGOTIATION_RECOMMENDATIONS DEFERRED — engine surfaces firm-by-firm spend; ML-driven negotiation recommendations future work
- INTERNAL_COUNSEL_COSTING META_ONLY — engine accepts internal hours but doesn't compute fully-loaded internal cost (HR salary load, benefits, overhead)

## Legal arc: 4 of 9 active. v10.174 next: ENH-226 Clause Library & Playbooks.
