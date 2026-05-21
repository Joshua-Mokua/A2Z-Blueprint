# CHANGELOG v10.43 — Risk arc · ENH-OR-001 (Operational Risk SMA)

**Status:** Risk arc OPEN · 5/6 batches complete (op_risk added; liquidity_stress + arc closure pending)
**Audit:** 128/128 PASS · **G128:** STABLE (309 modules · 765 imports · 3 HARD baseline)
**Active standards:** 116 / 259 · **Scenario library:** 42 (23 Risk-arc)

## New module

- `utils/op_risk.py` (~510 lines) — BCBS d457 §RBC30 Standardised Measurement
  Approach. Pure stdlib (`math` + `Decimal`); no scipy. Single public engine
  `OperationalRiskSMA` with `compute(SMAInputs) → SMAResult`.

## Computation pipeline

- **BI 3-year average** = mean of (ILDC + SC + FC) per year
  - ILDC = `min(|II−IE|, 0.0225×IEA) + DI` per §RBC30.10
  - SC   = `max(OI, OE) + max(FI, FE)` per §RBC30.11
  - FC   = `|Net P&L TB| + |Net P&L BB|` per §RBC30.13
- **Bucket assignment** (BI in EUR, marginal application):
  - Bucket 1: BI ≤ 1bn EUR → α₁ = 12%
  - Bucket 2: 1bn < BI ≤ 30bn EUR → α₂ = 15% on portion above 1bn
  - Bucket 3: BI > 30bn EUR → α₃ = 18% on portion above 30bn
- **BIC** = bucket-marginal Σ αᵢ × BI_i, computed in EUR then converted to KES
- **LC** = `15 × annual_avg_loss` over 10y window (caller-supplied events)
- **ILM** = `ln(e − 1 + (LC/BIC)^0.8)` per §RBC30.21
  - Forced to `1.0` in Bucket 1 when `apply_bucket_1_discretion=True` (§RBC30.41)
  - Forced to `1.0` when distinct loss-history years < 5 (insufficient history)
  - Source surfaced as enum `ILMSource ∈ {COMPUTED, BUCKET_1_DISCRETION, INSUFFICIENT_HISTORY}`
- **ORC** = BIC × ILM
- **RWA_op** = ORC × 12.5

## Rule 1 / Rule 7 alignment

- `SMAResult` surfaces: `bi_per_year_kes`, `bi_three_year_avg_kes`,
  `bi_three_year_avg_eur`, `bucket`, `bic_kes`, `annual_avg_loss_kes`,
  `lc_kes`, `ilm`, `ilm_source`, `orc_kes`, `rwa_op_kes`, `framework_refs`.
- Engine never auto-records loss events; never approves capital allocations;
  national-discretion override is a caller flag, not engine policy.
- Decimal-internal for all monetary outputs; float used only inside ILM
  (math.log) before conversion back to Decimal.

## Validation envelope

- `BusinessIndicatorInputs.__post_init__` rejects negative IEA.
- `OperationalLossEvent.__post_init__` rejects negative gross loss.
- `SMAInputs.__post_init__` enforces: exactly 3 BI years, distinct fiscal
  years, positive EUR/KES rate.

## Standards registry

- Appended to `TREASURY_ENHANCEMENT_STANDARDS` after ENH-CR-001:
  - **ENH-OR-001** · subcategory `audit` (per FROZEN list — op-risk has no
    own subcategory; nearest semantic fit is governance/audit) · priority A ·
    HIGH severity · `affected_engines=("op_risk",)` · v10.43.
- `standards_registry.self_test()` PASS · total 259 · active 116.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY` (`v10.43 — Operational Risk SMA`):

- **OR-01 Bucket 1 discretion** — small Kenyan bank, ILM forced to 1, ORC=BIC,
  RWA = ORC×12.5. 5 assertions.
- **OR-02 Insufficient history** — bucket 2 bank with only 2y of losses → ILM
  fallback to 1.0, source = INSUFFICIENT_HISTORY. 3 assertions.
- **OR-03 ILM monotonic** — same BIC, larger annual losses → larger ILM and
  larger ORC. Tests the formula's monotonicity property. 3 assertions.
- **OR-04 Provenance** — Rule 1 cross-check that all SMAResult fields
  populate, BCBS d457 ref present, ILM source enum surfaced. 4 assertions.

End-to-end runner: OR-01..OR-04 all PASS · 15/15 assertions.

## Self-tests

- `python3 utils/op_risk.py` → ✓ 17 tests.
- `python3 utils/standards_registry.py` → ✓ self-test PASS.
- `python3 utils/scenario_simulator.py` → ✓ 18 tests (no regression).

## Gate verification

- `python3 scripts/audit.py` → **Score: 128/128 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings match baseline
  exactly** (309 modules · 765 imports · 58 findings · HARD=3).

## Deferred to Risk arc closure (v10.45 expected)

- ENH-LR-001 liquidity_stress (next batch).
- G129 Risk arc closure ratchet test.
- Engine Hub Tier additions for the entire Risk arc (per Lean+Compact protocol).
- Master Prompt updates (per Lean+Compact protocol).

## Files changed

- **NEW** `utils/op_risk.py`
- **MOD** `utils/standards_registry.py` (+ENH-OR-001 entry, +30 lines)
- **MOD** `utils/scenario_simulator.py` (+4 scenarios + library extension)
- **NEW** `CHANGELOG_v10.43.md`
