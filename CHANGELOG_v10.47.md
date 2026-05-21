# CHANGELOG v10.47 — credit_model_risk arc opens · ENH-260 Alternative Credit Scoring

**Status:** Risk arc CLOSED · credit_model_risk arc OPEN (1/2 batches; ENH-268 governance pending)
**Audit:** 130/130 PASS · **G128:** STABLE (312 modules · 779 imports · 3 HARD baseline)
**Active standards:** 118 / 260 · **Scenario library:** 50 (4 ALT-* added)

## Why this batch

The Risk arc closed at v10.45 + UI backfilled at v10.46. The
registry survey showed `credit_model_risk` as the earliest-slipped
arc — 2 standards still tagged `status='planned'` against an
implementation_batch hint of `v10.33+`. v10.47 opens that arc by
shipping ENH-260; ENH-268 remains for v10.48; full closure batch
follows in v10.49 (G131 + Tier 25 + Master Prompt + UI cockpit per
the v10.46 protocol amendment).

## New module

- `utils/credit_alt_scoring.py` (~580 lines · 15 self-tests) —
  thin-file PD estimation via 3 alternative pillars per CGAP +
  Smart Campaign + IFC Inclusive Finance guidance. Pure stdlib
  (`math` + `Decimal`). Single public engine
  `AlternativeCreditScoringEngine.compute(applicant) → AltScoringResult`.
- Distinct from `utils.credit_risk_scoring` (Standard #53 — bureau
  PD/LGD/EAD) and `utils.credit_risk_irb` (ENH-CR-001 — regulatory
  IRB capital). Composes with both: alt-PD output flows into
  IRB capital via the same `pd` parameter when bureau data is
  later acquired.

## Computation pipeline

Three pillars; each produces a sub-PD AND a confidence weight
(0 when pillar unusable):

**Pillar 1 — TRANSACTION** (default weight 0.50)
- `monthly_deposit_cv` — high CV ≈ irregular cash flow
- `salary_cycle_signal` — recurring deposit pattern present?
- `expense_to_deposit_ratio` — high ≈ thin liquidity
- `bills_on_time_pct` — strong inverse signal
- Requires `months_observed ≥ 3`; sub-signal coverage drives
  pillar confidence.

**Pillar 2 — BEHAVIORAL** (default weight 0.30)
- `tenure_months` — longer ≈ lower risk
- `mobile_active_days_per_month` — engagement reduces estimated risk
- `current_facility_delinquency_days` — strongest single behavioral
  signal (0 / <30 / <60 / <90 / ≥90 day bands)
- Requires `tenure_months ≥ 1`; tenure depth (cap 24m) and signal
  coverage drive pillar confidence.

**Pillar 3 — PSYCHOMETRIC** (default weight 0.20)
- `risk_tolerance_score` — high tolerance ≈ riskier
- `time_horizon_score` — longer-term thinking ≈ lower risk
- Optional minimal questionnaire; requires at least one of the two
  scores to be usable.

**Aggregation:**
- Each pillar's signal contributions averaged then mapped to PD via
  `0.50 × signal^1.8` with floor at PD_FLOOR (3 bp, matches
  BCBS d424 IRB) and ceiling at 0.9999.
- Composite = confidence-weighted mean across usable pillars
  (eff_weight = base_weight × pillar_confidence, renormalised).
- Overall confidence = mean of (base_weight × pillar_confidence)
  across all 3 slots — penalises missing pillars structurally.
- Confidence band: HIGH (≥ 0.70) / MEDIUM (≥ 0.40) / LOW (< 0.40).
- Below LOW → `recommend_bureau_check=True` → underwriting escalates
  rather than acting on a thin estimate.

**Grade mapping:** PD → S&P-style grade via `RISK_GRADES` + `PD_BANDS`
re-imported from `utils.credit_risk_scoring` (no duplicate catalog).

## Rule 1 / Rule 7 alignment

- `AltScoringResult` surfaces: per-pillar `PillarScore` (pillar_pd +
  confidence_weight + features_used + skip_reason), composite_pd,
  grade, confidence_band, overall_confidence, missing_pillars,
  recommend_bureau_check, framework_refs, notes.
- Engine never auto-approves, never auto-declines, never writes to
  the credit bureau. Output feeds underwriting workflow + credit
  committee discussion. No mutation methods on `ApplicantData` or
  registry — `ThinFileApplicant`, `TransactionMetrics`,
  `BehavioralMetrics`, `PsychometricMetrics`, `PillarScore`, and
  `AltScoringResult` are all frozen dataclasses.

## Validation envelope

Construction-time checks:
- `TransactionMetrics`: `months_observed ≥ 0`, `bills_on_time_pct`
  in `[0, 1]`, `expense_to_deposit_ratio ≥ 0`.
- `BehavioralMetrics`: `tenure_months ≥ 0`,
  `current_facility_delinquency_days ≥ 0`,
  `mobile_active_days_per_month` in `[0, 31]`.
- `PsychometricMetrics`: both scores in `[0, 1]` when present.

Below-floor pillars surfaced via `skip_reason` ("only N months
observed; need ≥ 3", "tenure 0m below 1m minimum", etc.) — no
silent zeroing.

## Standards registry

- **ENH-260** activated: `status: planned → active`,
  `implementation_batch: v10.33+ → v10.47`,
  `affected_engines: ("credit_risk_scoring",) → ("credit_alt_scoring",)`,
  full description rewritten to capture the 3-pillar architecture
  and Rule 1 / Rule 7 contracts, `regulatory_source` updated from
  generic Continuation.docx to "CGAP + Smart Campaign + IFC + CBK
  PG/03".
- Registry self-test PASS · total 260 · active **117 → 118**.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY`:

- **ALT-01 Healthy thin-file** — strong signals across all 3
  pillars (12mo stable deposits + salary cycle + 24mo tenure + zero
  delinquency + low risk tolerance) → PD < 5%, HIGH confidence,
  no bureau escalation. 4 assertions.
- **ALT-02 Risky thin-file** — irregular deposits + 40% bills on
  time + 4mo tenure + 45-day delinquency → PD > 10%, BB-or-worse
  grade, psychometric pillar surfaced as missing per Rule 1.
  3 assertions.
- **ALT-03 Insufficient data** — only partial psychometric data
  → ConfidenceBand.LOW, `recommend_bureau_check=True`, two
  pillars surfaced as missing. 3 assertions.
- **ALT-04 Provenance** — Rule 1 cross-check: 3 PillarScore objects
  with features_used + skip_reasons, framework refs cite CGAP,
  caller notes preserved. 4 assertions.

End-to-end runner: ALT-01..ALT-04 all PASS · **14/14 assertions**.
Scenario library 46 → **50**.

## Self-tests

- `python3 -m utils.credit_alt_scoring` → ✓ 15 tests.
- `python3 -m utils.standards_registry` → ✓ self-test PASS.
- `python3 -m utils.scenario_simulator` → ✓ 18 tests (no regression).

## Gate verification

- `python3 scripts/audit.py` → **Score: 130/130 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings
  match baseline exactly** (312 modules · 779 imports · 59 findings
  · HARD=3). Module +1 (credit_alt_scoring) · imports +2.

## credit_model_risk arc state

| Batch    | Module              | Standards | Status |
| -------- | ------------------- | --------- | ------ |
| **v10.47** | credit_alt_scoring | ENH-260   | ✅      |
| pending  | credit_committee    | ENH-268   | ⏳      |
| pending  | arc closure (G131 + Tier 25 + Master Prompt + UI cockpit) | closure | ⏳ |

## Lean+Compact protocol — applied

- 1 ENH per batch (ENH-260) ✅
- ~580 line module (within ~400-600 target band) ✅
- CHANGELOG technical bullets only (this file) ✅
- Engine Hub Tier addition DEFERRED to closure ✅
- Master Prompt update DEFERRED to closure ✅
- UI integration page DEFERRED to closure (per v10.46 amendment) ✅
- Audit + G128 + scenario library extension SHIPPED (non-negotiable) ✅
- Per Rule 1 every pillar surfaces features_used + skip_reason ✅
- Per Rule 7 engine never auto-approves / declines / writes-to-bureau ✅
- Decimal-internal precision preserved for confidence weights ✅

## Files changed

- **NEW** `utils/credit_alt_scoring.py` (~580 lines, 15 self-tests)
- **MOD** `utils/standards_registry.py` (ENH-260 activated, ~30 lines
  description rewrite)
- **MOD** `utils/scenario_simulator.py` (+4 ALT-* scenarios + library
  extension)
- **NEW** `CHANGELOG_v10.47.md`

## Next batch

- **v10.48** — ENH-268 Credit Committee Governance
  (charter, voting rules, quorum, escalation matrix, policy-override
  tracking, decision rationale capture per CBK PG/03).
- **v10.49** — credit_model_risk arc closure (G131 ratchet + Tier 25
  Engine Hub + Master Prompt + UI cockpit page wiring both engines).
