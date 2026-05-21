# CHANGELOG v10.82 — ml_governance arc 2/N (ENH-282 MLOps Adjudication Log)

**Status:** Single batch. ml_governance arc 2 of 5. Sits at the integration point between the v10.76 ML hook contract and ENH-281 mlops_model_registry.

**Audit:** 138/138 PASS (closure ratchets at arc closure)
**G117:** STABLE
**G128:** STABLE
**Active standards:** 150/260 (was 149; +1 from ENH-282)
**Scenario library:** 174 (was 170; +4 from ADJ-01..04)
**Engine self-tests:** 148/148 (was 147; +1 from mlops_adjudication_log)

---

## Why this batch

The mlops_model_registry (v10.81) tracks which model version is deployed where. But it doesn't capture what happens after deployment — whether operators are accepting recommendations or overriding them, whether overrides cluster around specific recommendation classes (potential bias signal), whether the override patterns suggest the model is losing operator trust and needs retraining.

ENH-282 fills that gap. It's the operational feedback loop where production observation becomes retraining signal. The closed loop across the arc:

```
model serves prediction (v10.76 ML hook contract)
  → operator overrides or accepts (this engine captures)
    → ENH-283 retraining scheduler reads override rate trend (next drop)
      → ENH-281 registry receives new candidate version
        → ENH-284 A/B harness compares shadow vs active (planned)
          → ENH-285 model card composer surfaces all of the above (planned)
```

This is not a closed loop the engines drive — operators trigger every transition. The engines only surface the signals that justify the transitions. Per Rule 7, engine NEVER auto-retrains, NEVER auto-modifies model recommendations, NEVER silently records (every event is an explicit operator decision captured by the caller).

## What landed

`utils/mlops_adjudication_log.py` (~1300 lines, **21/21 tests pass**). Five capabilities, all caller-supplied-data discipline, all Rule 7 diagnostic-only.

### 1. record_adjudication

Validates a caller-supplied event description and constructs an `AdjudicationRecord` (frozen). Per Rule 7, engine never persists — caller appends to their adjudication storage. Validation includes:

- All required fields present (event_id, model_id, model_version, recommendation, recommendation_class, operator_decision, operator_id, decision_at_iso)
- ISO 8601 datetime format strict (regex-validated)
- **`OVERRIDDEN` status requires `override_reason`** — regulatory examination requires the reason to be captured at the moment of decision, not reconstructed afterward
- **`retraining_eligible=True` requires `input_features_hash`** — without it the example can't link back to training data for the next model version

Returns `RecordingOutcome.RECORDED` (with the constructed record) or `RecordingOutcome.REJECTED_INVALID` (with all validation findings surfaced — Rule 1, not just first failure).

### 2. compute_override_rate

Rolling override rate per model over caller-supplied `TimeWindow` (HOURS or DAYS unit). The denominator excludes PENDING (not yet decided) and ESCALATED (decided by senior reviewer outside the operator's scope). The numerator is OVERRIDDEN.

Per Rule 1, rate is `None` when `decided==0` (gap surfacing — engine never fabricates a rate from an empty denominator). Per Rule 7, engine never decides "rate too high → trigger retraining" — that's ENH-283 retraining scheduler territory (and even there the scheduler will surface signal; operator triggers).

### 3. compute_class_level_override_patterns

Per-recommendation-class override patterns. Caller supplies the class taxonomy: `RecommendationClassTaxonomy(class_id, description, is_protected_class, minimum_sample_size)`. Engine flags classes where `|class_rate - overall_rate| ≥ uneven_threshold_pct` (caller-supplied; default 0.20 = 20pp). Sample sufficiency required (caller-supplied minimum).

**The bias-signal vs bias-decision boundary is the critical Rule 7 line here.** This engine surfaces uneven override rates as a SIGNAL — the operator (and the model_governance arc at G124, which has the validated bias monitoring framework with demographic parity / equalized odds / calibration tests) DECIDES whether the signal indicates actual bias. The new mlops engine doesn't replicate G124's bias monitoring — it provides an additional input to it.

This boundary is preserved in `framework_refs` of the result: every output explicitly cites G124 as the bias-decision authority.

### 4. build_retraining_candidate_dataset

Composes a candidate retraining dataset from operator-overridden examples flagged `retraining_eligible`. Filters: `model_id` + status==OVERRIDDEN + `retraining_eligible=True` + `input_features_hash` present.

Per Rule 1, exclusions are surfaced as separate explicit counts:
- `examples_excluded_no_features_hash` — overridden + eligible but missing the hash
- `examples_excluded_not_eligible` — overridden but not flagged eligible

Caller sees what dropped out and why.

`insufficient_examples` flag below caller-supplied `minimum_count_threshold` — surfaces but does not block. Caller decides whether to proceed with insufficient data or wait.

Per Rule 7, engine selects + structures the dataset; never trains. Caller invokes the training pipeline. This is the deliberate split between observation (this engine) and action (training infrastructure).

### 5. build_adjudication_audit_trail

Chronological event list + summary statistics for regulatory examination evidence preservation. Sorted by `decision_at_iso`. Summary includes count_total/accepted/overridden/escalated/pending plus an `overridden_by_reason` breakdown showing which override reasons dominated in the window.

Per Rule 1, full event list + summary surface together — regulator sees both the rollup and the underlying events. Per Rule 7, engine composes the audit trail in a generic shape; never serializes to regulator-specific schemas (XBRL / iTax / CBK formats are `regulatory_reporting` territory). Caller decides serialization at exam time.

## 4 new scenarios ADJ-01..04

**ADJ-01** clean override capture — model recommended APPROVE, operator chose REJECT with DOMAIN_KNOWLEDGE reason, retraining_eligible=True with input_features_hash present. Full provenance preserved + lineage to training data.

**ADJ-02** override rate excludes PENDING from denominator — 4 records (1 ACCEPTED + 2 OVERRIDDEN + 1 PENDING). Rate = 2/3 (PENDING excluded since not yet decided). PENDING count surfaced separately. Engine never decides "rate too high → retraining" (ENH-283 boundary cited).

**ADJ-03** class-level uneven detection surfaces bias signal — APPROVE 50 decisions / 30% override rate (deviation 18.75pp from 48.75% overall, below 20pp threshold), REJECT 30 decisions / 80% override rate (deviation 31.25pp, above threshold). REJECT flagged uneven; APPROVE not. Engine surfaces signal; bias DECISION belongs to model_governance arc at G124. Boundary preserved.

**ADJ-04** retraining dataset filters with explicit exclusion counts — 1 included (eligible+hash), 1 excluded as not-eligible (surfaced explicitly per Rule 1), 1 ACCEPTED (not in candidates at all). insufficient_examples=True since 1 < 10 threshold. Engine selects + structures; never trains.

## Files changed in this drop

- **NEW** `utils/mlops_adjudication_log.py` (~1300 lines, 21 tests)
- **MOD** `utils/standards_registry.py` (ENH-282 added to MLOPS_GOVERNANCE_STANDARDS)
- **MOD** `utils/scenario_simulator.py` (4 ADJ scenarios + library wiring)
- **MOD** `pages/7_admin.py` (Tier 29 second entry)
- **NEW** `CHANGELOG_v10.82.md` (this file)

## ml_governance arc state

| Standard | Engine | Drop | Status |
|---|---|---|---|
| ENH-281 | mlops_model_registry | v10.81 | active |
| ENH-282 | mlops_adjudication_log | **v10.82** | **active** |
| ENH-283 | mlops_retraining_scheduler | next | planned |
| ENH-284 | mlops_ab_harness | TBD | planned |
| ENH-285 | mlops_model_card_composer | TBD | planned |

**2 of 5 active.** Three more drops to closure (~v10.85 with G139+G140 ratchet pair + closure cockpit page).

## What v10.83 would naturally cover

**ENH-283 MLOps Retraining Scheduler.** Diagnostic engine that consumes outputs from ENH-282 (override rate trends) + ENH-281 (model freshness — time since last training) + caller-supplied retraining policies, and surfaces when retraining is due.

Capabilities likely:
- `evaluate_retraining_freshness` — compare model age (now - training_completed_at_iso) against caller-supplied freshness threshold per model
- `detect_drift_signal` — consume override rate trend (caller integrates ENH-282 output) + model_governance.detect_drift_psi/ks/wasserstein outputs (caller integrates G124 outputs); surface integrated drift+override signal
- `validate_retraining_policy_compliance` — caller-supplied RetrainingPolicy (max_age_days + max_override_rate + max_drift_psi); flag policies that would block deployment
- `build_retraining_due_calendar` — given fleet of registered models + policies, surface calendar of when each model is due for retraining

Per Rule 7, engine never auto-triggers retraining. Surfaces "retraining is due" signal; operator + ML team decide.

The retraining scheduler is the thing that closes the loop between observation (ENH-282) and action (the next training run, which produces the next candidate registered via ENH-281). Single-batch scope, ~5 capabilities.

## Honest acknowledgements

**Override rate denominator policy is opinionated.** PENDING and ESCALATED both excluded. Some shops would include ESCALATED as "the model didn't have the right answer because senior had to step in." The current engine treats PENDING + ESCALATED as "didn't get a clean accept/reject decision from this operator" and excludes both. Future v10.83+ enhancement could parameterize denominator policy via a caller-supplied flag.

**Uneven-detection threshold is a single-number rule.** `|class_rate - overall_rate| ≥ uneven_threshold_pct` is a simple deviation check. More sophisticated approaches (chi-square test of independence, Cramer's V, statistical-significance-adjusted thresholds) would be more robust but introduce more complexity. The current rule is documented as a SIGNAL, not a bias decision; the bias decision lives at G124 where the proper statistical machinery is.

**Class taxonomy is caller-supplied without engine-side validation of class coverage.** If the caller's taxonomy lists APPROVE + REJECT but the records contain HOLD recommendations, those HOLD records are simply absent from the per-class report. Engine doesn't flag "your taxonomy doesn't cover all observed classes." Future enhancement could surface unmapped_classes as an explicit list (matches the ENH-276 connectivity engine's pattern).

**Time window arithmetic is naive.** The window's `end_iso` minus `duration` (HOURS or DAYS) is calculated via simple `timedelta`. No timezone awareness beyond ISO 8601 offset preservation, no leap-second handling, no DST consideration for DAYS unit. For typical override-rate windows (1-30 days), this is fine. For sub-second precision audit reconstruction, would need refinement.

**The audit trail summary doesn't include median time-to-decision.** A useful regulatory examination metric (how long from model recommendation to operator decision?) would require recording the recommendation timestamp separately from the decision timestamp. Current schema only tracks `decision_at_iso`. Future v10.83+ enhancement could add `recommended_at_iso` field for time-to-decision analysis.

**Retraining dataset construction doesn't deduplicate.** If the same input_features_hash appears multiple times in the override stream (same input adjudicated more than once with different operators), the dataset includes both. Caller decides whether to dedupe at training pipeline ingestion. Adding dedup logic to the engine would conflate "engine selects examples" with "engine cleans data" — keeping them separate is cleaner.

**No automatic integration with ENH-281 registry.** The adjudication engine doesn't verify that the model_id + model_version pair on each event corresponds to a registered model. That cross-check is operator workflow territory. Future v10.83+ enhancement could add a `validate_records_against_registry` capability that takes the registry sequence + records and surfaces orphaned events (referencing model versions not in the registry).

**Cleared to proceed to v10.83** ENH-283 retraining scheduler when ready.
