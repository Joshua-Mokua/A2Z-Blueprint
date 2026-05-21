# CHANGELOG v10.84 — ml_governance arc 4/N (ENH-284 MLOps A/B Comparison Harness)

**Status:** Single batch. ml_governance arc 4 of 5. The bridge from "we have a candidate registered via ENH-281 with status=SHADOW" to "the candidate is ready to be the active." One more drop until arc closure.

**Audit:** 138/138 PASS (closure ratchets at arc closure ~v10.85)
**Active standards:** 152/260 (+1 ENH-284)
**Scenario library:** 182 (+4 ABT scenarios)
**Engine self-tests:** 150/150 (+1 mlops_ab_harness)

---

## Why this engine is the candidate-evaluation bridge

The first three ml_governance arc engines each produce signals:
- ENH-281 mlops_model_registry — what's deployed (active vs candidate)?
- ENH-282 mlops_adjudication_log — how are operators reacting?
- ENH-283 mlops_retraining_scheduler — should we retrain?

What was missing is the engine that operates on the parallel prediction streams from ACTIVE and SHADOW deployments. Shadow deployment is a standard MLOps pattern: a candidate model processes the same input stream as the active model, producing predictions that are recorded but don't drive operator workflow. This lets you observe how the candidate would behave on real production data without risking actual decisions. ENH-284 takes those parallel streams and surfaces the deltas an operator needs to decide whether the candidate is ready.

The deliberate design choice is the same as the rest of the arc: **caller integrates the upstream**. The harness doesn't trigger inference. It doesn't subscribe to event streams. It takes pre-computed PredictionEvent sequences plus caller-supplied thresholds and produces a comparison report. This keeps the engine pure — same diagnostic-engine pattern that's now run through 14 closed arcs.

## What landed

`utils/mlops_ab_harness.py` (~1100 lines, **19/19 tests pass**). Five capabilities:

### 1. pair_predictions

Pair ACTIVE and SHADOW events by `input_features_hash` — the linchpin field that lets you tell "did both versions see the same input?" The pairing surfaces three categories:
- `paired` — both versions saw this input; PairedComparison record with active_class, shadow_class, agreement flag, latency_delta_ms
- `unpaired_active_only` — active saw this input but shadow didn't (could indicate sampling policy, routing bug, or shadow not fully deployed)
- `unpaired_shadow_only` — shadow saw this input but active didn't (could indicate phantom traffic, replayed test data leaking through)

Per Rule 1, all three lists surface explicitly. Operations diagnoses deployment skew rather than getting silent dropouts.

### 2. compute_agreement_summary

Aggregate per-pair agreement into a rate. Per Rule 1, **rate is None when no pairs** — engine never fabricates from an empty denominator. If total_paired==0, operator must investigate why (shadow not deployed? routing bug? active not running?) rather than getting a meaningless 0%.

### 3. compute_class_distribution_shift

Per-class share comparison across the two versions. The interesting Rule 1 surface: **classes appearing only in one side surface with the other side's count=0**. If shadow predicts a "HOLD" class that active never produces (because the previous model didn't have HOLD as an output), that novel class shows up explicitly with `active_count=0, shadow_count=N`. Engine never silently drops classes — operator sees the full picture including the new ones.

### 4. compute_latency_comparison

Median + p95 + max per version, plus deltas (median_delta_ms, median_delta_pct, p95_delta_ms). Implementation note: percentile computed via linear interpolation on sorted values without statistics module dependency — gives explicit control over edge cases (n=0, n=1, exact ranks, fractional ranks). For a list of 10 values [10..100], p95 = sorted[8] + 0.55 * (sorted[9] - sorted[8]) = 90 + 0.55 * 10 = 95.5. Per Rule 1, `insufficient_sample` flag surfaces when below caller-supplied minimum (default 30 — small enough to surface signal, large enough to be meaningful).

### 5. build_ab_comparison_report

Orchestrator. Composes pairing + agreement + distribution + latency + cost (when estimates supplied) + composite severity. Composite ABReportSeverity:
- **INSUFFICIENT_SAMPLE** — total_paired below caller's minimum_paired_sample
- **NOT_READY** — agreement_rate below critical_rate OR latency regression at/above critical_pct
- **NEEDS_REVIEW** — agreement below warning_rate OR latency regression at/above warning_pct
- **READY_TO_PROMOTE** — all checks within tolerance

Per Rule 7, the rationale **always cites ENH-281 validate_promotion_readiness as the actual promotion gate**. This is critical to the boundary: the A/B harness produces a summary view; ENH-281's PromotionGate evaluation (with caller-supplied gates) is the actual gate. READY_TO_PROMOTE doesn't mean "promote now" — it means "the comparison data doesn't show a blocking issue; now run your promotion gates."

## Rule 7 boundaries

Engine NEVER:
- Auto-promotes shadow to active (ENH-281 territory)
- Auto-deprecates active (ENH-281 territory)
- Decides which side is "better" (surfaces deltas; operator decides on each axis — agreement, distribution, latency, cost — separately)
- Executes inference itself (consumes pre-computed prediction streams from caller's inference infrastructure)
- Filters outliers or normalizes data (caller decides pre-processing policy; engine processes what's given)
- Persists prediction streams (caller stores)

## 4 new scenarios ABT-01..04

**ABT-01** pairing surfaces unpaired events explicitly — 2 paired (h1 agree, h2 disagree), 1 active-only (h3), 1 shadow-only (h4). Demonstrates deployment-skew diagnosis: operator sees inputs only one side processed.

**ABT-02** class distribution shift surfaces novel classes — active 70/30 APPROVE/REJECT, shadow 50/30/20 APPROVE/REJECT/HOLD (HOLD is novel). HOLD class surfaces with active_count=0. Engine never silently drops. APPROVE share delta -0.20 surfaces explicit shift magnitude.

**ABT-03** composite report NOT_READY on low agreement — 100 paired predictions with 50% agreement (below critical 0.70). Severity NOT_READY. Rationale cites the specific breach AND cites ENH-281 validate_promotion_readiness as actual promotion gate. Demonstrates the boundary.

**ABT-04** composite report READY_TO_PROMOTE with cost comparison — 100 paired with 95% agreement, 10% latency regression (within tolerance), cost estimates supplied. Severity READY_TO_PROMOTE. Cost delta surfaces (+KES 0.1 over the 100-call window). Rationale states operator should still run ENH-281 promotion gates before final promotion.

## Files changed

- **NEW** `utils/mlops_ab_harness.py` (~1100 lines, 19 tests)
- **MOD** `utils/standards_registry.py` (ENH-284 added to MLOPS_GOVERNANCE_STANDARDS)
- **MOD** `utils/scenario_simulator.py` (4 ABT scenarios + library wiring)
- **MOD** `pages/7_admin.py` (Tier 29 fourth entry)
- **NEW** `CHANGELOG_v10.84.md`

## ml_governance arc state

| Standard | Engine | Drop | Status |
|---|---|---|---|
| ENH-281 | mlops_model_registry | v10.81 | active |
| ENH-282 | mlops_adjudication_log | v10.82 | active |
| ENH-283 | mlops_retraining_scheduler | v10.83 | active |
| ENH-284 | mlops_ab_harness | **v10.84** | **active** |
| ENH-285 | mlops_model_card_composer | next | planned |

**4/5 active.** One more drop until arc closure (~v10.85 with G139+G140 ratchet pair + closure cockpit page + G141 cross-platform wiring gate + Master Prompt update).

## What v10.85 brings (arc closure batch)

The closure batch follows the established 5-thing pattern from trade_finance v10.80 and earlier:

1. **ENH-285 mlops_model_card_composer** — final engine. Per-model card composer that pulls together registry metadata (ENH-281) + drift status (model_governance G124) + override rate trend (ENH-282) + retraining cadence (ENH-283) + A/B comparison (ENH-284) into per-model documentation surfaces fit for regulatory examination.

2. **G139 + G140 closure ratchet pair** — G139 verifies all 5 mlops_* standards active with required symbols. G140 verifies arc-level scenario count ≥ 20 (4 per engine × 5 engines).

3. **G141 cross-platform wiring gate** — the audit-side answer to "apply this everywhere." The gate would enumerate utils/* modules using the v10.76 ML hook contract and verify each has a corresponding registry entry path + adjudication wiring path. Same enforcement pattern as G108/G109/G110 from older closed work — discipline becomes a property of the codebase, not just a checklist.

4. **Closure cockpit `pages/98_ml_governance_arc_cockpit.py`** — single pane of glass for ML operations: every registered model + override rate + drift signal + retraining-due calendar + A/B status + model card.

5. **Master Prompt v10.85 update + CHANGELOG_v10.85.md.**

## Honest acknowledgements

**The composite severity is opinionated.** Two breaches → NOT_READY; one warning breach → NEEDS_REVIEW. Some shops would want stricter rules ("any latency regression at all → NEEDS_REVIEW") or weighted scoring across the four axes. The current rule prioritizes correctness (agreement) over performance (latency) and treats them as independent thresholds. Caller can extend by ignoring composite severity and applying their own logic to the surfaced data.

**The pairing key is a hash.** This works when caller computes deterministic hashes over the canonical feature representation. If two callers compute hashes differently for the same logical input (different ordering of dict keys, different float precision, different text normalization), pairing breaks silently. Documented as caller responsibility; the engine treats hashes as opaque identifiers.

**Multiple predictions on same input hash isn't blocked.** If the same input appears twice in the active stream (same hash), the harness uses the first one. This is unusual in practice — typically each prediction event has a unique input — but defensive callers should dedupe upstream. Future enhancement could surface duplicate_hash_count as an explicit flag.

**Latency stats use Decimal arithmetic throughout.** This is consistent with the platform's Decimal discipline and avoids floating-point representation issues, but it means callers who measure latency in float milliseconds need to convert at the engine boundary. The strictness catches subtle issues (a percentile computation that rounds at different points across versions) at the cost of one extra conversion call.

**No native integration with cross_sell_bandit (ENH-126) or credit_explainability (ENH-263).** Those engines exist outside the v10.76 ML hook contract pattern (the bandit predates v10.76; credit_explainability lives in the model_governance arc). Wiring them through ENH-281/282/283/284 is operations work — they need to be retrofit to register their model artifacts and capture operator overrides. The G141 wiring gate (planned for v10.85) would surface them as ML touch points needing wiring; the actual retrofit lands post-arc-closure.

**Cost comparison is naive multiplication.** `cost_per_call_kes * call_count` for each version. Doesn't account for variable cost components (different infrastructure tiers, different model sizes, different memory footprints). Caller can supply more sophisticated cost models via richer CostEstimate fields in a future enhancement.

**P95 percentile uses linear interpolation, not nearest-rank.** Different shops use different conventions. Linear interpolation is the more common modern choice (matches numpy's default `linear` interpolation method); nearest-rank would give different boundary values. Documented as the engine's choice; caller should be aware their other latency tools may report slightly different p95 numbers on the same data.

**Cleared to proceed to v10.85 — ENH-285 model card composer + arc closure batch** when ready.
