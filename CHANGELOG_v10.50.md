# CHANGELOG v10.50 — revenue_assurance arc OPENS · ENH-241 Validation Agents

**Status:** revenue_assurance arc 1/8+1 batches (7 standards remaining + closure)
**Audit:** 132/132 PASS · **G128:** STABLE (315 modules · 788 imports · 3 HARD baseline)
**Active standards:** 119 → **120** / 260 · **Scenario library:** 54 → **58** (4 RA-* added)

## Why this batch

After credit_model_risk closed at v10.49 under the v10.46-amended
protocol (registry ratchet + UI cockpit shipped together), the
roadmap's earliest slipped arc is **revenue_assurance** — 8 standards
tagged `v10.40+` but still planned (10 versions behind schedule).
v10.50 opens the arc by shipping ENH-241, the foundational data
integrity engine. The remaining 7 standards (ENH-242..248) compose
on top of it. Closure at ~v10.58 follows the v10.46 template:
G-gate ratchet + UI ratchet + Tier 26 + Master Prompt + cockpit page.

## New module

- `utils/revenue_validation.py` (~745 lines · 19 self-tests) —
  diagnostic engine producing `ValidationFinding` objects across
  four agent-style routines. Pure stdlib (`Decimal` + `statistics`
  + frozen dataclasses + enums). Single public engine
  `RevenueValidationEngine` exposing four agent methods plus a
  `validate_all` orchestrator.

## Architecture

The four "agents" are class methods on a single engine, not
autonomous threads — same pattern as `treasury_agents.py` (ENH-240),
where `Recommendation` objects are produced but human approval gates
every action. This module produces `ValidationFinding` objects; the
caller (and downstream ENH-243 orchestrator) triages them.

### Agent 1 — SCHEMA validation
- `amount_kes > 0` (revenue is positive — refunds/reversals belong
  in a separate `REVERSAL` feed; conflating them silently corrupts
  totals).
- `revenue_category` must be in `ALLOWED_REVENUE_CATEGORIES`
  (6 values: INTEREST_INCOME / FEE_INCOME / COMMISSION_INCOME /
  FX_INCOME / TRADING_INCOME / OTHER_INCOME).
- `posting_date` not in the future beyond `FUTURE_DATE_TOLERANCE_DAYS`
  (default 1 day — accommodates timezone drift but rejects 2027
  postings entered today as a likely keystroke error).

### Agent 2 — COMPLETENESS check
- Compares actual records against an `ExpectedCount` manifest.
- Buckets by `(period, dimension_key, revenue_category)` where
  `dimension_key` is `branch=X` or `product=Y`.
- Missing entire bucket (count=0 vs expected>0) → HIGH.
- Count mismatch (count>0 but ≠ expected) → MEDIUM.
- Exact match → no finding.
- Caller-supplied `period_extractor` callable (default YYYY-MM
  from posting_date).

### Agent 3 — CROSS-SOURCE reconciliation
- Pairwise reconciliation of `CrossSourceTotal` aggregates between
  any two sources (e.g., CBS vs GL, GL vs regulatory return).
- Default tolerance 5 bp (`Decimal("0.05")`); tunable per call.
- Four finding types:
  - **mismatch_amount** (MEDIUM): both present, `|A − B| > tolerance × max(A, B)`.
  - **mismatch_count** (LOW): totals match within tolerance but
    record counts differ — possible netting or grouping difference.
  - **missing_a** / **missing_b** (HIGH): present in one source only.
- Caller can pass `tolerance_pct=Decimal("0")` for exact-match
  discipline (zero tolerance rejected as `< 0`; zero is allowed).

### Agent 4 — STATISTICAL anomaly screen
- Z-score outlier detection within `(revenue_category, branch_code)`
  groups.
- Default `z_threshold=3.0`, `min_sample_size=10`.
- Groups smaller than `min_sample_size` are skipped (z-score is not
  meaningful below this threshold) — surfaced as no finding rather
  than false negative.
- `|z| ≥ z_threshold` → MEDIUM; `|z| ≥ z_threshold + 2` → HIGH.
- This is the **upstream data-quality screen**; ENH-242 will add
  ML-based pattern detection downstream. The scope boundary is
  intentional: this engine catches "data looks weird"; ENH-242
  will catch "data follows known fraud patterns".

### Orchestrator — `validate_all`
- Runs all four agents in sequence; empty inputs for any agent
  produce zero findings of that category (rather than failing).
- Returns a `ValidationReport` with per-agent counts, severity
  distribution, total records validated, and framework refs.

## Rule 1 / Rule 7 alignment

- All 6 dataclasses are frozen: `RevenueRecord`, `CrossSourceTotal`,
  `ExpectedCount`, `ValidationFinding`, `ValidationReport` (plus
  `field` import unused but kept for forward compatibility).
- Every `ValidationFinding` surfaces: `finding_id`, `severity`,
  `category`, `record_id_or_batch_id`, `description`, `expected`,
  `observed`, `source_system`, `posting_date`, `framework_refs`,
  `notes`. A human investigator can reproduce the issue from the
  finding alone — no need to re-query the engine for context.
- Engine never:
  - mutates input records (frozen dataclasses make this physically
    impossible)
  - writes to source systems
  - auto-closes findings
  - silently drops records (invalid records still appear in the
    finding's `record_id_or_batch_id`; nothing is hidden)

## Validation envelope

Construction-time checks:
- `RevenueRecord.__post_init__` rejects empty `record_id` /
  `source_system`.
- `ExpectedCount.__post_init__` rejects `expected_count < 0`.
- `reconcile_sources` rejects `tolerance_pct < 0`.
- `detect_anomalies` rejects `z_threshold ≤ 0` and
  `min_sample_size < 3`.

## Standards registry

- **ENH-241** activated: `status: planned → active`,
  `implementation_batch: v10.40+ → v10.50`,
  `affected_engines: ("revenue_assurance",) → ("revenue_validation",)`.
  Description rewritten from generic stub to capture the 4-agent
  architecture, severity / category enums, frozen dataclasses, and
  Rule 1 / Rule 7 contracts. `regulatory_source` updated from
  generic Continuation.docx to "CBK PG/03 §revenue +
  reconciliation discipline".
- Registry self-test PASS · total 260 · active **119 → 120**.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY` (which is the central
library despite the legacy name — every arc adds here):

- **RA-01 Clean records** — 10 valid records → 0 schema findings,
  0 CRITICAL severity, all records validated. Baseline happy path.
  3 assertions.
- **RA-02 Schema violations** — 3 violations (negative amount →
  CRITICAL, unknown revenue_category → HIGH, future posting_date →
  HIGH) → 3 SCHEMA findings, severity distribution verified, no
  silent dropping per Rule 7. 4 assertions.
- **RA-03 Cross-source reconciliation** — CBS vs GL across 3
  categories: FEE_INCOME within 5bp tolerance → no finding,
  INTEREST_INCOME 10% diff → MEDIUM amount-mismatch, FX_INCOME
  present in GL only → HIGH missing-in-CBS. 4 assertions.
- **RA-04 Statistical anomaly** — 12 normal records around
  1000-1200 + 1 outlier at 100000 → anomaly agent flags the
  outlier with z-score in observed field, framework refs cite
  z-score screening. 4 assertions.

End-to-end runner: RA-01..RA-04 all PASS · **15/15 assertions**.
Scenario library 54 → **58**.

## Self-tests

- `python3 -m utils.revenue_validation` → ✓ 19 tests covering
  validation envelope, all 4 agent routines, edge cases (small
  groups, zero-tolerance rejection, frozen-record contract),
  orchestrator behaviour, and Rule 1 provenance presence.
- `python3 -m utils.scenario_simulator` → ✓ 18 tests (no regression).
- `python3 -m utils.standards_registry` → ✓ self-test PASS.

## Gate verification

- `python3 scripts/audit.py` → **Score: 132/132 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings
  match baseline exactly** (315 modules · 788 imports · 61 findings
  · HARD=3). Module +1 (revenue_validation), imports +1.

## Lean+Compact protocol — applied (v10.46 amended)

- 1 ENH per batch (ENH-241) ✅
- ~745 line module (test count drove the size — same pattern as
  op_risk and liquidity_stress; trimming would weaken coverage)
- Engine Hub Tier addition DEFERRED to closure ✅
- Master Prompt update DEFERRED to closure ✅
- UI integration page DEFERRED to closure (per v10.46 amendment) ✅
- Audit + G128 + scenario library extension SHIPPED (non-negotiable) ✅
- Per Rule 1 every ValidationFinding surfaces full provenance ✅
- Per Rule 7 engine diagnostic only — no auto-correct / auto-write /
  auto-close ✅

## Files changed

- **NEW** `utils/revenue_validation.py` (~745 lines, 19 self-tests)
- **MOD** `utils/standards_registry.py` (ENH-241 activated, ~37 line
  description rewrite)
- **MOD** `utils/scenario_simulator.py` (+4 RA-* scenarios + library
  extension)
- **NEW** `CHANGELOG_v10.50.md`

## Honest scope notes

1. **`ALLOWED_REVENUE_CATEGORIES` is a 6-value tuple constant** —
   not an enum. A multi-bank platform may need to add categories
   per local regulator; tuple-as-vocabulary is more flexible than
   an enum, but loses the IDE auto-complete + exhaustive-match
   benefits. Future enhancement could promote to enum if Ecobank's
   chart of accounts settles.

2. **Anomaly detection is statistical only.** Z-score outliers
   surface "data that doesn't look like the rest of the same group" —
   useful as upstream screen but blind to known fraud patterns
   (e.g., split deposits just below reporting threshold). ENH-242
   adds the ML-based pattern detection layer; v10.50 leaves that
   gap intentionally to keep this engine deterministic and
   auditable.

3. **Single-pass agents** — completeness manifest is fully
   pre-computed by caller. Recurring-pattern detection (e.g.
   "branch X usually posts 28 records but only 15 this month — even
   though we didn't have a manifest entry") would need a
   historical-baseline layer not shipped here. Could be ENH-243
   orchestrator scope.

4. **No partner/supplier reconciliation logic** — that's
   ENH-244 scope. ENH-241 reconciles internal sources (CBS, GL,
   regulatory return); cross-counterparty work belongs downstream.

## Next batch — roadmap

- **v10.51** — ENH-242 Anomaly Agents (Pattern Detection): ML-based
  revenue anomaly detection — leakage patterns, billing errors,
  commission miscalculation, rate-card breaches. Composes with
  this engine's statistical screen (z-score outliers feed pattern
  detector as candidates).
- **v10.52** — ENH-243 Revenue Agentic Orchestrator: orchestration
  layer over validation + anomaly agents; auto-prioritizes
  findings, assigns to investigators, tracks remediation. (Per
  Rule 7, "assigns" means produces work-item records — never
  acts on the source data.)
- **v10.53..v10.57** — ENH-244..ENH-248 sequentially.
- **v10.58** — revenue_assurance arc closure under v10.46 protocol:
  G133 ratchet + G134 UI ratchet + Tier 26 + Master Prompt +
  `pages/95_revenue_assurance_cockpit.py`.
