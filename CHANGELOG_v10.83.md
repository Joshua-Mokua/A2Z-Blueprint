# CHANGELOG v10.83 — ml_governance arc 3/N (ENH-283 MLOps Retraining Scheduler)

**Status:** Single batch. ml_governance arc 3 of 5. The integration point that consumes ENH-281 (registry — for active model age) + ENH-282 (adjudication — for override rate) + model_governance G124 (drift detection — for distribution drift) and surfaces "retraining is due" recommendations.

**Audit:** 138/138 PASS (closure ratchets at arc closure)
**Active standards:** 151/260 (+1 ENH-283)
**Scenario library:** 178 (+4 RTR scenarios)
**Engine self-tests:** 149/149 (+1 mlops_retraining_scheduler)

---

## Why this is the integration engine

The first two ml_governance arc engines each track one thing:
- ENH-281 mlops_model_registry — what's deployed?
- ENH-282 mlops_adjudication_log — what did operators decide?

The model_governance arc (closed at G124) tracks one more: is the model SAFE to deploy? (validation + bias + drift detection algorithms).

What was missing is the engine that **combines these three signals** against a policy and surfaces a retraining-due decision. ENH-283 is that engine. It doesn't compute drift itself (that's G124's PSI/KS/Wasserstein implementations). It doesn't compute override rate itself (that's ENH-282). It doesn't track model age itself (that's ENH-281). It composes the three into a single recommendation.

The deliberate design choice: **caller integrates the upstream outputs**. The scheduler doesn't directly read from registry storage or adjudication storage or call drift functions. It takes pre-computed signal values + caller-supplied thresholds + caller-supplied policy. This preserves the caller-supplied data discipline that's now run through the entire arc.

## What landed

`utils/mlops_retraining_scheduler.py` (~1100 lines, **22/22 tests pass**). Five capabilities:

### 1. evaluate_freshness
Given `training_completed_at_iso` + `as_of_iso` + caller-supplied `FreshnessPolicy(warning_age_days, stale_age_days)`, compute current age and classify into FRESH/WARNING/STALE. Per Rule 1, **INSUFFICIENT_DATA surfaces explicitly** when `training_completed_at_iso` is missing or unparseable — engine never fabricates an age. This handles the canonical case of legacy models registered before training instrumentation was added.

### 2. evaluate_override_signal
Given current override rate (caller integrates ENH-282 `OverrideRateMetric.override_rate`) + `OverrideThresholds(warning_rate, critical_rate)`. Per Rule 1, **INSUFFICIENT_DATA preserved when rate is None** rather than defaulting to OK. Absence of data is not absence of concern — operator may need to investigate why no decisions were made.

### 3. evaluate_drift_signal
Given current drift metric (caller integrates `model_governance.detect_drift_psi/ks/wasserstein` output) + `DriftThresholds(warning_value, critical_value, metric_name)`. **The engine never decides which drift method to use** — caller supplies the chosen metric + thresholds calibrated to that method. The metric_name field is provenance-only (engine doesn't switch behavior on it). This preserves G124's authority over drift detection methodology.

### 4. compute_retraining_recommendation
Orchestrator. Combines three signals + caller-supplied `RetrainingPolicy(require_freshness, require_override_signal, require_drift_signal)`. Outcome:
- **DUE** — at least one signal at CRITICAL or STALE severity
- **SOON** — at least one at WARNING but no CRITICAL
- **NOT_YET** — all signals OK / FRESH
- **INSUFFICIENT_DATA** — required signal returned INSUFFICIENT_DATA

Required vs not-required matters: a *required* signal returning INSUFFICIENT_DATA propagates to the overall outcome; a *non-required* signal returning None is silently skipped. Per Rule 1, every contributing signal surfaces in the rationale + the underlying assessment dataclasses are preserved on the recommendation (operator sees the full picture).

### 5. build_retraining_calendar
Given a fleet of recommendations, returns `RetrainingCalendar` sorted by urgency rank: DUE (rank 0) → SOON (1) → NOT_YET (2) → INSUFFICIENT_DATA (3). Summary counts surface alongside per-model entries. Per Rule 7, **calendar is a view, not a schedule** — engine never executes retraining. ML team uses calendar for capacity planning; operator decides when to trigger.

## Rule 7 boundaries

Engine NEVER:
- Auto-triggers retraining (operator + ML team execute the next training run, which produces a candidate registered via ENH-281)
- Auto-promotes a candidate (ENH-281 territory)
- Auto-deprecates an active (ENH-281 territory)
- Reads ENH-281 / ENH-282 / model_governance state directly (caller integrates outputs)
- Persists scheduler state (caller stores recommendations if persistence is desired)
- Decides which drift method to use (caller supplies chosen metric)

## 4 new scenarios RTR-01..04

**RTR-01** freshness STALE drives DUE — 8-month-old model, severity STALE, recommendation DUE. Engine surfaces severity but never auto-triggers (Rule 7 boundary cited).

**RTR-02** INSUFFICIENT_DATA propagation — legacy model with no training timestamp → freshness INSUFFICIENT_DATA → recommendation INSUFFICIENT_DATA when require_freshness=True. Engine surfaces missing signal explicitly rather than defaulting to NOT_YET.

**RTR-03** three-signal combination — FRESH + CRITICAL override + CRITICAL drift drives DUE. Demonstrates that production observation overrides freshness signal alone. All three contributions surface in rationale per Rule 1.

**RTR-04** fleet calendar sorts by urgency — 3 models (stale=DUE, warn=SOON, ok=NOT_YET) ordered correctly. Summary counts surface alongside per-model entries. Calendar is view-not-schedule per Rule 7.

## Files changed

- **NEW** `utils/mlops_retraining_scheduler.py` (~1100 lines, 22 tests)
- **MOD** `utils/standards_registry.py` (ENH-283 added)
- **MOD** `utils/scenario_simulator.py` (4 RTR scenarios)
- **MOD** `pages/7_admin.py` (Tier 29 third entry)
- **NEW** `CHANGELOG_v10.83.md`

## ml_governance arc state

| Standard | Engine | Drop | Status |
|---|---|---|---|
| ENH-281 | mlops_model_registry | v10.81 | active |
| ENH-282 | mlops_adjudication_log | v10.82 | active |
| ENH-283 | mlops_retraining_scheduler | **v10.83** | **active** |
| ENH-284 | mlops_ab_harness | next | planned |
| ENH-285 | mlops_model_card_composer | TBD | planned |

**3/5 active.** Two more drops to closure (~v10.85 with G139+G140 + closure cockpit + G141 cross-platform wiring gate).

## What v10.84 covers

**ENH-284 MLOps A/B Harness** — shadow-vs-active deployment delta surfacing before promotion. Given two model versions (current ACTIVE + candidate SHADOW from ENH-281) running in parallel against the same input stream, surface delta in:
- Per-prediction outcome agreement rate (how often shadow agrees with active)
- Per-class outcome distribution shift (does shadow predict the same class mix?)
- Latency comparison (does shadow run faster/slower?)
- Cost comparison (when caller supplies cost-per-call estimates)
- Operator override rate comparison (consume ENH-282 outputs filtered to each version)

Per Rule 7, engine never auto-promotes the shadow to active — surfaces the deltas, operator decides via ENH-281's `validate_promotion_readiness`.

## Honest acknowledgements

**The combination logic is opinionated.** Any CRITICAL/STALE → DUE; any WARNING → SOON; all OK → NOT_YET. Some shops would prefer weighted scoring (e.g., critical override + warning drift + warning freshness → DUE because override is highest weight). The current rule is the simplest defensible default; future v10.84+ enhancement could add a `combination_strategy` parameter for caller-supplied combiner Callable (matches the v10.76 ML hook pattern).

**Required vs non-required signals is a binary flag, not a weight.** A more sophisticated policy could specify "freshness contributes 30%, override 50%, drift 20%, requiring at least 70% of contributing weight to declare DUE." That's flexible but more complex. The current binary required/not-required covers the canonical cases (freshness always required for any model with training timestamp; override + drift required when production data is reliable).

**Default policy is conservative.** `require_freshness=True` only — most permissive default that still catches the most important case. Caller almost certainly wants stricter policies in production. Documented as "for first-use convenience; caller REPLACES via constructor."

**Calendar urgency rank doesn't account for business criticality.** A DUE retraining for a low-traffic model ranks ahead of a SOON retraining for the credit_scorer that handles 10K decisions/day. Future v10.84+ enhancement could add a `business_criticality` field to RetrainingCalendarEntry that callers populate from their own knowledge.

**No automatic integration with ENH-281 registry.** Per Rule 7 + caller-supplied data discipline, this is intentional. But it means the caller has to invoke `lookup_active_version` from ENH-281, then call `evaluate_freshness` here, then assemble. A future cockpit-page helper could compose these into a one-call flow without violating the engine boundary.

**No INSUFFICIENT_DATA cascade in calendar.** If 5 of 10 models in the fleet return INSUFFICIENT_DATA, the calendar shows 5 INSUFFICIENT entries at the bottom. Operations sees the gap. Future enhancement could surface "5 of 10 models lack required signals" as a fleet-level health metric, but that crosses into reporting concerns that probably belong in the closure cockpit (~v10.85), not this engine.

**Cleared to proceed to v10.84 ENH-284 A/B harness** when ready.
