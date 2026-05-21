# CHANGELOG v10.42 — CREDIT RISK IRB CAPITAL (BCBS d424 §RBC25)

**Audit:** 128/128 PASS — 124th consecutive clean.
**Tests:** 16 self-tests on `credit_risk_irb` + 59 v10.39+v10.40 integration tests + 19 Risk-arc scenarios (51/51 assertions).
**G128 baseline:** STABLE (308 modules · 764 imports · 3 HARD unchanged).
**Active standards:** 115 / 258.

## What v10.42 ships

`utils/credit_risk_irb.py` (~600 lines, 16 self-tests) — Basel III IRB regulatory capital per BCBS d424 §RBC25 corporate exposure formula. **Distinct from** existing modules:
- `credit_risk_scoring.py` — underwriting (loan origination)
- `ifrs9_classification.py` — accounting (Stage 1/2/3 ECL)
- `credit_risk_irb.py` — **regulatory capital** (Pillar 1 RWA computation)

1 ENH standard activated:

| ID | Title | Engine |
|---|---|---|
| ENH-CR-001 | IRB Capital Framework (PD/LGD/EAD/RWA) | `credit_risk_irb` |

Subcategory: `credit` (existing — no new subcategory needed).

## The math (pure stdlib, no scipy)

```
K = LGD × [N((1-R)^-0.5 × N^-1(PD) + (R/(1-R))^0.5 × N^-1(0.999)) - PD]
        × (1 + (M-2.5) × b(PD)) / (1 - 1.5 × b(PD))

R = 0.12 × W + 0.24 × (1-W)   where W = (1-exp(-50×PD)) / (1-exp(-50))
b(PD) = (0.11852 - 0.05478 × ln(PD))^2

RWA = K × 12.5 × EAD
EL  = PD × LGD × EAD
```

99.9% confidence per Basel ASRF (§RBC25.4). Implemented via `statistics.NormalDist`.

## Constraints enforced at construction

| Input | Range | Source |
|---|---|---|
| PD | [0.0003, 1.0] | §RBC25.6 (3 bps floor) |
| LGD | [0, 1] | — |
| EAD | > 0 | — |
| M | [1, 5] | §RBC25.13 |
| ExposureClass | LARGE_CORPORATE / SME_CORPORATE only in v10.42 | scope limit |

## 4 IRB-* scenarios extending library 34 → 38

- **IRB-01:** typical corporate (PD=1%, LGD=45%, M=2.5y, 10m) → K∈[4%,12%], EL=45k, R∈[0.12, 0.24]
- **IRB-02:** defaulted exposure (PD=1.0) → K=0 above EL per §RBC25.16
- **IRB-03:** K monotonic in PD (0.5% → 2% → 10%)
- **IRB-04:** portfolio aggregation — RWA totals match per-exposure sum

9 assertions all green.

## Lean-mode protocol

- One ENH standard this batch (was 2-3 in earlier Risk batches)
- ~600 line module (was 800-1100)
- Engine Hub Tier 24 deferred to Risk arc closure
- Master Prompt update deferred to Risk arc closure
- Standalone integration test file skipped — self-tests + scenarios cover all paths
- No new audit gate (mid-arc)

## Honesty Rule conformance

- Rule 1: every `CapitalResult` surfaces all inputs (PD/LGD/EAD/M) + intermediate values (correlation R, maturity adjustment b) + outputs (K, RWA, EL) + framework_refs.
- Rule 7: engine is computational only — never moves loans between exposure classes, never auto-approves capital allocations. Approvals flow through ALCO + Capital Management Committee.
- Decimal-internal precision for all monetary outputs; float for probability inputs (`statistics.NormalDist` requires float).

## Honest scope notes

- **Sovereign and Bank exposure classes deferred.** v10.42 covers corporate scope only (LARGE_CORPORATE + SME_CORPORATE). Sovereign uses zero-floor risk weights; Bank exposures use distinct correlation per §RBC25.10. Future batch.
- **Retail exposure class deferred.** Per §RBC25.20 retail uses different correlation structure (no maturity adjustment, fixed R=0.15 or 0.04 by sub-class). Future batch.
- **No portfolio-level diversification benefit.** Aggregate RWA is simple sum across exposures. Pillar 2 economic capital with diversification is future scope.
- **PD/LGD inputs caller-provided.** Module does not estimate PD or LGD — those come from `credit_risk_scoring` (underwriting) or downstream rating engines. Per Rule 7, engine never overrides inputs.

## Phase 2

| Arc | Status | Active |
|---|---|---|
| 9 closed arcs | closed | 91 |
| Cross-arc infra | infra | — |
| Risk arc — Foundation + Limits + Boundary + IRB | OPEN | 11 |
| Op risk / Liquidity stress | pending | 0 |

Next likely v10.43 Operational Risk (RCSA + loss events + Basel SMA capital) OR v10.44 Liquidity Stress Testing (composes with `treasury_alm`).
