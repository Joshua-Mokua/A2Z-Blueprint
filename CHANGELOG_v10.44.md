# CHANGELOG v10.44 — Risk arc · ENH-LR-001 (Stressed LCR)

**Status:** Risk arc OPEN · 6/7 batches complete (liquidity_stress added; G129 closure ratchet pending)
**Audit:** 128/128 PASS · **G128:** STABLE (310 modules · 766 imports · 3 HARD baseline)
**Active standards:** 117 / 260 · **Scenario library:** 46 (27 Risk-arc)

## New module

- `utils/liquidity_stress.py` (~600 lines) — BCBS d295 §40-§69 stressed LCR
  with severity-tiered run-off calibration. Pure stdlib `Decimal`. Single
  public engine `LiquidityStressEngine` with `compute(...) → StressedLCRResult`.
- Distinct from existing `utils.liquidity_risk` (Standard #73 baseline LCR/NSFR)
  and `utils.stress_testing` (Standard #79 capital stress). Constants are
  mirrored, not imported, so the new module adds zero new import edges into
  legacy code paths.

## Computation pipeline

- **HQLA per level + caps**:
  - Haircuts: L1=0%, L2A=15%, L2B=50%
  - L2B cap: ≤15% of total HQLA → enforced as `(15/85) × (L1 + L2A_after_haircut)`
  - L2 cap: L2A + L2B ≤ 40% of total HQLA → enforced as `(40/60) × L1`
  - When L2B exceeds its standalone cap, L2A is trimmed proportionally; if
    L2B alone exceeds the L2 cap, L2A drops to zero (rare edge surfaced via
    capped fields).
- **Stressed flows**:
  - Outflow stressed rate = `min(base_rate × severity_mult, 1.0)`
  - Inflow stressed rate = `min(base_rate × inflow_mult, 1.0)`
  - Per-category `StressedFlow` records (category_id, label, balance, base
    rate, multiplier, stressed rate, stressed KES) for full Rule 1 surfacing.
- **NCO**: `total_outflows − min(total_inflows, 0.75 × total_outflows)` per
  BCBS d295 §69 inflow cap.
- **LCR**: `HQLA_after_caps / NCO`, returned as `Optional[Decimal]` —
  `None` when NCO ≤ 0 (per Rule 1, no false-precision ratios).
- **Survival horizon**: `HQLA / (NCO/30)` days when LCR < 100%; `None`
  when compliant.

## Severity calibration

| Severity   | Outflow ×  | Inflow ×  |
| ---------- | ---------- | --------- |
| BASELINE   | 1.0        | 1.0       |
| MODERATE   | 1.5        | 0.85      |
| SEVERE     | 2.0        | 0.65      |
| BANK_RUN   | 3.0        | 0.40      |

Caller may also supply `outflow_rate_overrides: Mapping[str, Decimal]` to
substitute per-category base rates before stress multipliers are applied —
supports supervisor-mandated scenarios without modifying engine internals.

## Breach classification

| LCR band              | Severity   |
| --------------------- | ---------- |
| ≥ 100%                | COMPLIANT  |
| [90%, 100%)           | AMBER      |
| [70%, 90%)            | RED        |
| < 70%                 | CRITICAL   |

## Rule 1 / Rule 7 alignment

- `StressedLCRResult` surfaces: severity, `hqla_breakdown` (per-level gross +
  haircut + after-haircut), pre-cap and post-cap totals, L2/L2B capped values,
  per-category outflow/inflow `StressedFlow` records, total/in/out and
  inflows-capped, NCO, LCR ratio, breach severity, survival days, framework
  refs, caller notes.
- Engine never auto-liquidates HQLA, never executes funding draws, never
  rebalances category assignments. Severity calibration is data-driven
  (`SEVERITY_MULTIPLIERS` table); caller can override per-category base rates.
- All monetary outputs Decimal-quantized to KES 0.01.

## Validation envelope

- `HQLAHolding` / `OutflowCategory` / `InflowCategory` reject negative
  balances and rates outside [0, 1] at construction.
- LCR returns `None` when NCO ≤ 0; `BreachSeverity.COMPLIANT` is set on the
  None case (ratio absence is not a breach).

## Standards registry

- Appended to `TREASURY_ENHANCEMENT_STANDARDS` after ENH-OR-001:
  - **ENH-LR-001** · subcategory `treasury` · priority A · CRITICAL severity ·
    `affected_engines=("liquidity_stress",)` · v10.44.
- `standards_registry.self_test()` PASS · total 260 · active 117.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY`:

- **LR-01 BASELINE compliant** — well-capitalised bank, baseline severity,
  COMPLIANT, no survival horizon. 4 assertions.
- **LR-02 SEVERE escalation** — same inputs, BASELINE vs SEVERE: outflows
  rise, inflows fall, LCR ratio strictly worsens. Tests stress-overlay
  monotonicity. 3 assertions.
- **LR-03 BANK_RUN** — thin HQLA + idiosyncratic-run severity → breach
  classified, survival horizon populated, stressed retail rate capped at
  100%, LCR < 100%. 4 assertions.
- **LR-04 Provenance** — Rule 1 cross-check that per-category outflows,
  pre/post-cap HQLA totals, inflows-capped (≤75% of outflows), BCBS d295
  framework refs, and caller notes all populate. 5 assertions.

End-to-end runner: LR-01..LR-04 all PASS · 16/16 assertions.

## Self-tests

- `python3 utils/liquidity_stress.py` → ✓ 18 tests.
- `python3 utils/standards_registry.py` → ✓ self-test PASS.
- `python3 utils/scenario_simulator.py` → ✓ 18 tests (no regression).

## Gate verification

- `python3 scripts/audit.py` → **Score: 128/128 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings match
  baseline exactly** (310 modules · 766 imports · 60 findings · HARD=3).
- Modules +1 (liquidity_stress) · imports +1 · SOFT findings +2 (within
  baseline tolerance — HARD unchanged is the locked invariant).

## Risk arc — current state

| Batch    | Module                      | Standards            | Status |
| -------- | --------------------------- | -------------------- | ------ |
| v10.39   | market_risk_factors / sens / var | ENH-MR-001..005 | ✅      |
| v10.40   | market_risk_limits          | ENH-MR-006/007       | ✅      |
| v10.41   | trading_book_boundary       | ENH-MR-008/009/010   | ✅      |
| v10.42   | credit_risk_irb             | ENH-CR-001           | ✅      |
| v10.43   | op_risk                     | ENH-OR-001           | ✅      |
| v10.44   | liquidity_stress            | ENH-LR-001           | ✅      |
| pending  | Risk arc closure (G129)     | ratchet test         | ⏳      |

## Deferred to Risk arc closure (next batch)

- G129 Risk arc closure ratchet test (locks 9 active Risk-arc standards).
- Engine Hub Tier additions for the entire Risk arc (per Lean+Compact protocol).
- Master Prompt updates (per Lean+Compact protocol).

## Files changed

- **NEW** `utils/liquidity_stress.py`
- **MOD** `utils/standards_registry.py` (+ENH-LR-001 entry, ~33 lines)
- **MOD** `utils/scenario_simulator.py` (+4 scenarios + library extension)
- **NEW** `CHANGELOG_v10.44.md`
