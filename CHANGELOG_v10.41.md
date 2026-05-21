# CHANGELOG v10.41 — TRADING BOOK BOUNDARY (FRTB §A.4)

**Audit:** 128/128 PASS — 123rd consecutive clean.
**Tests:** 59 Risk-arc integration tests pass + 22 self-tests on `trading_book_boundary`.
**G128 baseline:** STABLE (307 modules · 763 imports · 3 HARD unchanged).
**Active standards:** 114 / 257.

## What v10.41 ships

`utils/trading_book_boundary.py` (1124 lines, 22 self-tests) — instrument classification (Trading Book vs Banking Book) per BCBS d352 FRTB §A.4 + §RBC25.

3 ENH-MR-* standards activated:

| ID | Title | Engines |
|---|---|---|
| ENH-MR-008 | Trading Book Boundary Classification | `trading_book_boundary` |
| ENH-MR-009 | Trading Desk Structure & Limits | `trading_book_boundary` |
| ENH-MR-010 | Boundary Reclassification Workflow | `trading_book_boundary` |

5 BOUNDARY-* scenarios (29 → 34 in TREASURY_SCENARIO_LIBRARY):

- BOUNDARY-01: listed equity for trading → TRADING_BOOK classification
- BOUNDARY-02: hedge of banking-book loan → BANKING_BOOK with hedge_designation
- BOUNDARY-03: ambiguous instrument → PENDING with reclassification queue
- BOUNDARY-04: 4-eye approval workflow for boundary changes
- BOUNDARY-05: trading-desk validation (intent + 3-month proof of trading)

15 assertions across the 5 scenarios all green.

## Lean-mode protocol applied

- Engine Hub Tier 23 deferred to Risk arc closure
- Master Prompt update deferred to Risk arc closure
- Standalone integration test file skipped — self-tests + scenarios cover all paths
- No new audit gate (mid-arc, same as v10.40)

## Honesty Rule conformance

- Rule 1: every BoundaryClassification carries instrument_id + classification + intent_attestation + framework_refs + approval_state
- Rule 7: classification is diagnostic; reclassification requires 4-eye approval; engine never auto-moves instruments between books

## Phase 2

| Arc | Status | Active |
|---|---|---|
| 9 closed arcs | closed | 91 |
| Cross-arc infra | infra | — |
| Risk arc — Foundation + Limits + Trading Book Boundary | OPEN | 10 |
| Credit / Op risk / Liquidity stress | pending | 0 |

Next likely v10.42 Credit Risk Foundation (PD/LGD/EAD per BCBS d424 IRB).
