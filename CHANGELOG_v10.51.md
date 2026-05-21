# CHANGELOG v10.51 — revenue_assurance arc · ENH-242 Anomaly Agents (Pattern Detection)

**Status:** revenue_assurance arc 2/8+1 batches (6 standards remaining + closure)
**Audit:** 132/132 PASS · **G128:** STABLE (316 modules · 790 imports · 3 HARD baseline)
**Active standards:** 120 → **121** / 260 · **Scenario library:** 58 → **62** (4 PAT-* added)

## New module

- `utils/revenue_anomaly_patterns.py` (~960 lines · 21 self-tests) —
  pattern-detection layer over ENH-241 data-integrity foundation.
  Pure stdlib (`Decimal` + frozen dataclasses + enums). Single
  public engine `RevenueAnomalyPatternEngine` exposing 6
  deterministic detectors plus an optional ML hook.

## Architecture

Where ENH-241 catches "data looks weird" (z-score outliers, schema
violations), ENH-242 catches "data follows known revenue-leakage
patterns". The two engines compose by sharing the `RevenueRecord`
dataclass (imported here, defined there) — no duplication.

### Six deterministic detectors

| Detector | Pattern ID | Family | Severity logic |
| -------- | ---------- | ------ | -------------- |
| `detect_duplicate_billings` | DUPLICATE_BILLING | BILLING_ERROR | 2 records → MEDIUM; 3+ → HIGH |
| `detect_unauthorized_waivers` | UNAUTHORIZED_FEE_WAIVER | LEAKAGE | HIGH (revenue at risk) |
| `detect_expired_contract_billing` | EXPIRED_CONTRACT_BILLING | LEAKAGE | ≤30d late → MEDIUM; >30d → HIGH |
| `detect_rate_card_breaches` | RATE_BELOW_FLOOR / RATE_ABOVE_CEILING | RATE_CARD_BREACH | floor breach → MEDIUM (leakage); ceiling breach → HIGH (compliance — overcharging) |
| `detect_missing_tax` | MISSING_TAX_COMPONENT | BILLING_ERROR | missing actual → HIGH; mismatch → MEDIUM |
| `detect_commission_anomalies` | COMMISSION_OVERPAYMENT / UNDERPAYMENT | COMMISSION_MISCALC | both halves of spectrum surface |

Each detector takes `Sequence[RevenueRecordWithContext]` (or a
related collection like `ContractRate` / `CommissionRecord`) and
returns `Tuple[PatternFinding, ...]`. Findings are immutable.

### ML hook — Rule 6 / Rule 7 discipline

Matches the established `utils.credit_risk_scoring` pattern
(Standard #53):

- Optional `ml_score_fn: Callable[[RevenueRecordWithContext], Optional[Decimal]]`
- When **absent** → `ml_disabled=True` and `ml_disabled_reason`
  populated in the report. **No silent fallback** — callers cannot
  mistake rule-only output for ML-augmented output.
- When **present** → engine calls the hook per record; scores ≥
  threshold (default 0.80) surface as `ML_FLAGGED_PATTERN` findings
  with the score in `ml_score` and `confidence` fields.
- ML scores ≥ 0.95 surface as HIGH severity; otherwise MEDIUM.
- ML hook raises an exception → engine catches and surfaces an
  INFO-severity finding citing the exception class + message rather
  than silently swallowing. Per Rule 6 — failures must be visible.

The engine never trains a model. The model is always external,
injected, and the engine treats it as an opaque scoring function.

### Tolerances

- Commission match: KES 1.00 (tighter than rounding noise; not zero)
- Tax match: 1% of expected, capped at KES 100 floor
- Rate card: exact match against `[floor, ceiling]` (banks tune
  via the `ContractRate` itself, not via global tolerance)

## Rule 1 / Rule 7 alignment

- All 5 dataclasses frozen: `ContractRate`, `RevenueRecordWithContext`,
  `CommissionRecord`, `PatternFinding`, `AnomalyReport`.
- Every `PatternFinding` surfaces: `finding_id`, `pattern_id`,
  `family`, `severity`, `record_ids` (tuple — every involved
  record), `description`, `evidence` (rule firing trace),
  `confidence`, `ml_score` (when applicable), `framework_refs`,
  `notes`. A human investigator can reproduce from the finding
  alone.
- Engine never:
  - auto-recovers leaked revenue
  - auto-reverses duplicate billings
  - auto-corrects rates outside the band
  - auto-closes findings
  - silently drops records with insufficient context (rules that
    need missing context simply skip rather than fire false
    positives)

### Composition with ENH-241

The `RevenueRecord` dataclass is **imported** from
`utils.revenue_validation`, not redefined. Same for
`ValidationSeverity` enum (reused by both engines). Two
implications:

1. Cross-arc structural integrity — refactoring `RevenueRecord`
   in ENH-241 propagates automatically; G128 catches any divergence.
2. The orchestrator (ENH-243, next batch) can take findings from
   both engines and compose them without translation.

## Validation envelope

Construction-time checks:
- `ContractRate.__post_init__` rejects empty `contract_id`,
  `floor_rate_pct < 0`, `ceiling_rate_pct < floor_rate_pct`,
  `effective_to < effective_from`.
- `CommissionRecord.__post_init__` rejects empty `commission_id`,
  any negative monetary field.
- `detect_with_ml` rejects `ml_threshold` outside `(0, 1]`.

## Standards registry

- **ENH-242** activated: `status: planned → active`,
  `implementation_batch: v10.40+ → v10.51`,
  `affected_engines: ("revenue_assurance",) → ("revenue_anomaly_patterns",)`.
  Description rewritten from generic stub to capture the 6
  detectors, 4 PatternFamily, 9 PatternId enums, ML-hook
  discipline, and Rule 1 / Rule 7 contracts.
- Registry self-test PASS · total 260 · active **120 → 121**.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY`:

- **PAT-01 Duplicate billing** — 3 records share (cust-A, KES 1500,
  2026-04-01) → 1 DUPLICATE_BILLING finding, HIGH severity (3+
  records), all 3 record_ids surfaced. 4 assertions.
- **PAT-02 Rate-card breach** — Contract C-001 [3.0%, 8.0%]:
  applied 2.0% → RATE_BELOW_FLOOR (MEDIUM leakage); applied 5.0%
  → no finding; applied 9.5% → RATE_ABOVE_CEILING (HIGH compliance
  breach). 3 assertions.
- **PAT-03 Commission anomalies** — over (paid 6000 vs expected
  5000), under (paid 3500 vs expected 4000), within tolerance
  (5000.50 vs 5000). 2 findings, both halves of spectrum
  surfaced. 3 assertions.
- **PAT-04 ML disabled (Rule 6 cross-check)** — `detect_all`
  without `ml_score_fn` returns `ml_disabled=True` + non-empty
  reason; rule-based detectors still fire (unauthorized waiver
  flagged); records_scanned reflected. **No silent fallback**. 4
  assertions.

End-to-end runner: PAT-01..PAT-04 all PASS · **14/14 assertions**.
Scenario library 58 → **62**.

## Self-tests

- `python3 -m utils.revenue_anomaly_patterns` → ✓ 21 tests covering
  validation envelope, all 6 deterministic detectors, ML hook (with
  + without model + with raising model), orchestrator behaviour,
  and Rule 1 provenance presence.
- `python3 -m utils.revenue_validation` → ✓ 19 tests (no regression).
- `python3 -m utils.scenario_simulator` → ✓ 18 tests (no regression).
- `python3 -m utils.standards_registry` → ✓ self-test PASS.

## Gate verification

- `python3 scripts/audit.py` → **Score: 132/132 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings
  match baseline exactly** (316 modules · 790 imports · 62 findings
  · HARD=3). Module +1 (revenue_anomaly_patterns), imports +2
  (RevenueRecord + ValidationSeverity from ENH-241).

## Lean+Compact protocol — applied (v10.46 amended)

- 1 ENH per batch (ENH-242) ✅
- ~960 line module (test breadth drove size — 21 tests covering 6
  detectors + ML hook variants)
- Engine Hub Tier addition DEFERRED to closure ✅
- Master Prompt update DEFERRED to closure ✅
- UI integration page DEFERRED to closure (per v10.46 amendment) ✅
- Audit + G128 + scenario library extension SHIPPED (non-negotiable) ✅
- Per Rule 1 every PatternFinding surfaces full provenance ✅
- Per Rule 6 ML-disabled state surfaced explicitly — no silent
  fallback ✅
- Per Rule 7 engine diagnostic only — no auto-recover / reverse /
  correct / close ✅
- Decimal-internal precision for monetary thresholds ✅

## Files changed

- **NEW** `utils/revenue_anomaly_patterns.py` (~960 lines, 21 self-tests)
- **MOD** `utils/standards_registry.py` (ENH-242 activated, ~37 line
  description rewrite)
- **MOD** `utils/scenario_simulator.py` (+4 PAT-* scenarios + library
  extension)
- **NEW** `CHANGELOG_v10.51.md`

## Honest scope notes

1. **No actual ML model shipped.** The standard says "ML-based"
   but per Rule 7 the engine ships only the hook. A production
   deployment would inject a trained model (gradient boosting on
   labelled historical data is the typical choice for this kind
   of anomaly detection). The engine's contribution is the
   integration discipline — Rule 6 surfacing, exception handling,
   confidence/score plumbing — not the model itself.

2. **No "missing recurring fee" detector.** The standard's
   leakage examples include "expected fee not posted" (e.g.,
   monthly account fee for accounts that should be charged but
   weren't). That belongs to ENH-241's completeness check
   (`ExpectedCount` manifest comparison) rather than here. Pattern
   detection looks at what *was* posted; completeness looks at
   what *should* have been posted but isn't.

3. **Duplicate detection is deliberately strict.** Same
   (customer, amount, date) flags as a finding; in practice some
   banks post multiple identical fees on one day legitimately
   (e.g., same fee for two cards). The detector surfaces these as
   candidates with HIGH severity for triplicates, MEDIUM for
   duplicates — humans confirm or dismiss. False positives are
   acceptable; false negatives (missed duplicate billing leakage)
   are not.

4. **Rate-card detector requires `applied_rate_pct`.** Records
   without this field are silently skipped (no false positives
   from records that don't have the context the detector needs).
   Production CBS extracts must populate this field for the
   detector to find anything.

5. **ML hook only fires LEAKAGE-family findings.** Future
   refinement could let the hook surface findings in any family
   (e.g., a model trained on commission anomalies surfaces
   COMMISSION_MISCALC). Current design keeps ML outputs in a
   single family for clean triage; adjust later if production
   shows the constraint biting.

## Next batch — roadmap

- **v10.52** — ENH-243 Revenue Agentic Orchestrator: composes
  ENH-241 + ENH-242 findings, prioritises by severity × pattern
  family × monetary impact, produces work-item assignments per
  Rule 7 ("assigns" = produces work records, never acts on source
  data).
- **v10.53..v10.57** — ENH-244..ENH-248 sequentially.
- **v10.58** — revenue_assurance arc closure under v10.46 protocol:
  G133 ratchet + G134 UI ratchet + Tier 26 + Master Prompt +
  `pages/95_revenue_assurance_cockpit.py`.

**133 consecutive clean batches.** 11 closed arcs holding;
revenue_assurance arc at 2/8 + closure pending.
