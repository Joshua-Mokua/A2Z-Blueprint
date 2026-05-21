# CHANGELOG v10.78 — trade_finance arc batch 8 (8/12) + ML training reference

**Status:** Dual-equivalent drop. ENH-270 AI-Powered Document Checking engine + reference ML training pipeline. The training script counts as the "second batch" in scope-equivalent terms — it's the architectural artifact this drop has been building toward across the entire v10.x ML thread.

**Audit:** 136/136 PASS (unchanged — closure-batch ratchets at v10.80)
**G117:** 99.0% (195/197) (unchanged)
**G128:** STABLE (345 modules · 879 imports · HARD=3) (+2 modules, +2 imports from new engine + reorg)
**Active standards:** 145/260 (was 144; +1 from this drop)
**Scenario library:** 158 (was 154; +4 from this drop — DOC-01..04)
**Engine self-tests:** 144/144 via orchestrator (was 143; +1 from this drop)

---

## Why this drop matters

This is where the v10.76 ML hook contract gets its real production-shaped test. Every prior ML mention in the codebase has been scaffolding — type hints in v10.76, pattern documentation, test cases that prove the hook integrates correctly. ENH-270 is the first engine where ML is genuinely the architectural difference between "good enough" rules-based output and "actually useful" trained classification on a long-tail problem.

The selling point this drop establishes — and the one that matters for Ecobank conversations — is no longer "we have ML scaffolding" but "we have a complete ML-extensible engine plus a working reference training pipeline that produces deployable models." The pipeline shape is the deliverable. What it produces depends on what data feeds it; the architecture is independent of that.

## v10.78a — ENH-270 AI-Powered Document Checking (ML-extensible)

**Module:** `utils/trade_finance_document_checking.py` (~1100 lines, 25/25 tests pass)

Diagnostic UCP 600 document examination engine for LC drawdown presentations. Two-layer architecture: deterministic UCP 600 rule-based checks emit `CandidateFinding` objects when potential discrepancies are detected; an optional ML hook refines severity and filters false positives via the v10.76 contract.

### The five capabilities

**1. `check_amount_tolerance`** — UCP 600 §30 amount tolerance. Default ±5% when LC silent, configurable per LC. Over-amount = HIGH severity (significant); under-amount = LOW (often acceptable as partial drawdown); missing-amount-field = CRITICAL. Returns `feature_hints` (`category=amount_over`, `ratio=1.10`) the ML classifier can use as features.

**2. `check_dates_and_periods`** — UCP 600 §6 expiry (CRITICAL — refusal almost certain), §29 latest shipment date (HIGH — requires waiver), §14(c) presentation period (default 21 days after shipment, HIGH). Each finding surfaces `days_late` as a numeric feature for ML scoring.

**3. `check_required_documents_present`** — Every `DocumentType` in `LC.required_documents` must appear at least once. Missing = CRITICAL.

**4. `check_cross_document_consistency`** — UCP 600 §14(d): data in any document must not conflict with data in any other document. Currently checks currency consistency (HIGH), port-of-loading and discharge consistency (MEDIUM), and description-of-goods overlap on the commercial invoice via 60% token-overlap heuristic (MEDIUM). The 60% threshold is deliberately conservative because false positives here annoy operators; the ML hook is the right place to refine borderline cases.

**5. `assess_presentation`** — Orchestrator. Runs all 4 checks, collects `CandidateFinding` stream, applies the ML classifier (or statistical fallback), returns `PresentationAssessment` with finalized `DiscrepancyFinding` tuple + 5-tier `PresentationOutcome` (CONFORMING / DISCREPANT_WAIVABLE / DISCREPANT_REFUSAL_LIKELY / REFUSED / INSUFFICIENT_DATA).

### How the ML hook actually integrates

The hook signature follows the v10.76 contract:

```python
ml_discrepancy_classifier: Optional[
    Callable[[Sequence[CandidateFinding]],
             Sequence[ClassificationResult]]] = None
```

Each `ClassificationResult` carries:
- `refined_severity` — the classifier's call (may differ from rule-assigned)
- `is_true_discrepancy` — false-positive filter; classifier can mark a candidate as "not actually discrepant" and the engine drops it from the final findings
- `confidence` — 0..1, surfaced in every finding for operator interpretation
- `reasoning` — human-readable; appears in `framework_refs`

When the hook is **absent**, `_classify_candidates` promotes every candidate to a `DiscrepancyFinding` using `rule_assigned_severity` directly, marking each `method=STATISTICAL_FALLBACK` and `ml_disabled=True`. This is the deterministic floor the engine ships with — UCP 600 categorical rules running at full strength, no ML required.

When the hook is **injected and succeeds**, candidates flow through it. `is_true_discrepancy=False` filters out false positives entirely (operator never sees them). `refined_severity` overrides the rule's initial guess. Every output marks `method=ML_INJECTED` and `ml_disabled=False`. Confidence surfaces in every finding.

When the hook is **injected but fails** — raises an exception, returns wrong-length output — the engine catches the failure, falls back to statistical, marks every output `method=STATISTICAL_FALLBACK` and `ml_disabled=True`, and includes a fallback note in `framework_refs` explaining what failed. This is the production-safety guarantee: a corrupt model artifact, sklearn version mismatch, or runtime exception in the classifier never crashes the engine. The deterministic UCP 600 rules always run; ML is additive.

### What this proves about the architecture

The DOC-01..04 scenarios cover all three states explicitly:
- **DOC-01** — clean presentation, no hook, `overall_ml_disabled=True`, zero findings → CONFORMING
- **DOC-02** — late presentation, no hook, fallback path → CRITICAL EXPIRY → DISCREPANT_REFUSAL_LIKELY
- **DOC-03** — over-tolerance amount, ML hook downgrades HIGH→LOW based on training data, outcome shifts from REFUSAL_LIKELY to WAIVABLE; `confidence=0.72` surfaced exactly
- **DOC-04** — same late-presentation case as DOC-02 but with a broken ML classifier; engine falls back gracefully, CRITICAL EXPIRY preserved through fallback, outcome unchanged at REFUSAL_LIKELY

The DOC-04 case is the architectural insurance policy. Production never depends on ML being available or correct. The deterministic rules are the floor.

**Per Rule 7, engine NEVER:** approves drawdowns (operator examines + decides per UCP 600 §16 within 5 banking days); issues notice of refusal (banking workflow territory); communicates with beneficiary or applicant; parses PDFs / OCRs documents (upstream structured-extraction territory — engine consumes `PresentedDocument` with already-extracted fields); retrains models in-place (training is separate infrastructure — see scripts/training/); mutates inputs.

## v10.78b — Reference ML training pipeline

**Script:** `scripts/training/train_document_classifier.py` (~580 lines)
**Dependencies:** `requirements-ml.txt` (sklearn + numpy on top of runtime requirements.txt)

End-to-end ML training pipeline. Demonstrates how a trained classifier gets produced, validated, and persisted for injection into ENH-270.

Seven stages:

1. **Data extraction (synthetic, replace in production)** — generates 2000 synthetic LC presentations via parameterized perturbation, runs each through ENH-270's deterministic checks to extract candidate findings. **In production this stage is replaced** with extraction of historical examiner adjudications from the bank's adjudication store. The current implementation emits `(CandidateFinding, label_severity, is_true_discrepancy)` triples from synthetic data.

2. **Feature engineering** — converts each `CandidateFinding` to a 22-dimensional numeric feature vector. One-hot encoded category (13 dims) + one-hot encoded rule severity (5 dims) + 4 numeric features extracted from `feature_hints` (days_late, amount_ratio, overlap_pct, distinct_count). The `FEATURE_NAMES` tuple is frozen at training time so inference uses the exact same feature vector layout — this is the contract that lets the trained model plug into the engine without ambiguity.

3. **Synthetic labeling (REPLACE IN PRODUCTION)** — applies a deliberately trivial rule-based labeling derived from `rule_assigned_severity` plus a 5% noise injection. Documented in script header as pipeline-validation-only. **The trained model achieves 100% test accuracy on this synthetic labeling, which is the expected pathological behavior, not a real success metric** — the model is trivially memorizing the feature it was given. This is exactly the "synthetic memorization trap" warned against in the v10.77 review of ML strategy.

4. **Stratified train/test split** — deterministic seed (default 42), default 80/20 split, stratified by severity label so rare classes are preserved in both sets.

5. **Training** — sklearn `LogisticRegression` baseline with `max_iter=1000`, `solver=lbfgs`. Swappable for any sklearn-API-compatible classifier (RandomForest, XGBoost, LightGBM) without changing the rest of the pipeline.

6. **Evaluation** — accuracy + macro precision + macro recall + macro F1 on held-out test set; full confusion matrix per severity tier; bootstrap 95% CI on accuracy via 1000 resamples (the only honest accuracy claim is one with confidence intervals).

7. **Persistence** — pickle model + metadata JSON. Metadata includes training date, random seed, sample counts, all metrics, feature names, label order, model artifact SHA-256 hash for integrity verification, sklearn version, explicit synthetic-trained disclosure, framework_refs noting v10.76 contract + Rule 6 + Rule 7.

### Why sklearn isn't in the runtime

The production runtime engine is **pure stdlib**. Adding sklearn to `requirements.txt` would impose a 60MB dependency on every deployment that runs the trade finance arc, regardless of whether they have a trained model to inject. Instead, sklearn lives in `requirements-ml.txt` for training environments — banks running the platform install it only when they're ready to train.

This is the same discipline that keeps the engine pure. The engine consumes a `Callable`. How that callable was produced — sklearn, pytorch, internal training infrastructure, or a hand-coded heuristic during prototyping — is invisible to the engine. The training pipeline ships as reference architecture; production deployments swap data sources and retrain.

### What the script does NOT claim

The synthetic-trained model is **demonstration grade**, never production grade. Every output of the script is documented with that status. The metadata JSON `data_source` field reads:

> SYNTHETIC — generated by scripts/training/train_document_classifier.py for pipeline validation only. NOT trained on real adjudication data. Production deployment requires retraining on operator adjudication history.

When real adjudication data becomes available — when Ecobank or any deployment has accumulated enough examiner adjudications to form a supervised training set — the data-extraction stage gets replaced and the model retrained. Pipeline architecture stays identical. The selling point shifts from "we have a working pipeline" (today) to "we have measured X% accuracy on Y banking days of your adjudication data" (post-deployment).

### Trying it out

```bash
pip install -r requirements-ml.txt    # one-time training-env setup
python scripts/training/train_document_classifier.py \
    --output-dir data/models/document_classifier \
    --random-seed 42 \
    --test-fraction 0.2 \
    --n-samples 2000 \
    --version 1
```

Or `--dry-run` to see metrics without writing artifacts. Output:
- `data/models/document_classifier/model_v1.pkl`
- `data/models/document_classifier/metadata_v1.json`

To inject the trained model into the engine, write a thin wrapper that loads the pickle and adapts to the `Callable[[Sequence[CandidateFinding]], Sequence[ClassificationResult]]` signature, then construct `TradeFinanceDocumentCheckingEngine(ml_discrepancy_classifier=wrapper)`.

## 4 new scenarios (DOC-01..04)

All 4 pass with 16/16 assertions:

- **DOC-01** clean conforming presentation — outcome CONFORMING, zero findings, UCP 600 cited
- **DOC-02** late presentation (after expiry) — CRITICAL EXPIRY, statistical fallback (no hook), outcome DISCREPANT_REFUSAL_LIKELY
- **DOC-03** ML hook injected and refining — over-tolerance amount HIGH→LOW per training data, outcome shifts WAIVABLE, confidence 0.72 surfaced exactly
- **DOC-04** ML hook fails (RuntimeError) — graceful fallback preserves CRITICAL EXPIRY, ml_disabled=True, outcome unchanged

DOC-03 + DOC-04 are the v10.76 contract proof in production-realistic shape. Same engine, three states (no hook / hook works / hook fails), three different `method` values, three different outcomes — and in every case the engine produces correct, defensible output.

## Tier 28 expansion

Tier 28 label updated to `(v10.70-v10.78, in flight, closes vTBD)`. New entry appended after `trade_finance_sustainability`:
- `trade_finance_document_checking` / `TradeFinanceDocumentCheckingEngine` — full description with two-layer architecture explained, ML hook contract noted, training pipeline reference

Tier 28 now has **8 of 12 expected entries**. Closure batch v10.80 adds the remaining entries (ENH-271 + ENH-276 + ENH-279 scope-resolution note + closure cockpit page).

## Files changed in this drop

- **NEW** `utils/trade_finance_document_checking.py` (~1100 lines, 25 tests)
- **NEW** `scripts/training/train_document_classifier.py` (~580 lines)
- **NEW** `requirements-ml.txt` (training-environment deps)
- **MOD** `utils/standards_registry.py` (ENH-270 activated, comprehensive description)
- **MOD** `utils/scenario_simulator.py` (4 new DOC scenarios + library wiring)
- **MOD** `pages/7_admin.py` (Tier 28 +1 entry, label v10.70-v10.78)
- **NEW** `CHANGELOG_v10.78.md` (this file)

## Trade finance arc state

| Standard | Engine | Drop | Status |
|---|---|---|---|
| ENH-269 | trade_finance_instruments | v10.70 | active |
| ENH-273 | trade_finance_limits | v10.71 | active |
| ENH-272 | trade_finance_swift | v10.72 | active |
| ENH-274 | trade_finance_compliance | v10.73 | active |
| ENH-275 | trade_finance_accounting | v10.75 | active |
| ENH-280 | trade_finance_reporting | v10.76 | active |
| ENH-278 | trade_finance_sustainability | v10.77 | active |
| ENH-270 | trade_finance_document_checking | **v10.78** | **active** |
| ENH-271 | (corporate trade portal) | v10.79 | next |
| ENH-276 | (multi-bank connectivity) | v10.79 | next |
| ENH-279 | (mobile app) | v10.80 | scope note in closure batch |
| (closure) | trade_finance_arc_cockpit | v10.80 | closure batch |

**8 of 12 active.** Two drops to closure. Trade finance becomes the 14th closed arc at v10.80.

## What's next — v10.79 dual batch

ENH-271 Corporate Trade Portal (data-layer engine; the UI portion rolls into closure cockpit) + ENH-276 Multi-Bank Connectivity (diagnostic adapter surface for we.trade / Marco Polo / Contour / Bolero — engine validates inbound message structures, never sends). Both deterministic — neither benefits from ML. The ML thread is now complete for the trade finance arc; the v10.76 contract has been demonstrated end-to-end.

## What's next — post-trade-finance ML governance arc

After v10.80 closure, the proper place to plan an ML governance arc — drift monitoring + model registry + adjudication feedback loop + scheduled retraining cadence + A/B comparison against rule-based baselines + model card per deployed model. Roughly 4-5 focused drops on its own cadence. The reference training script in this drop is one piece of that arc; the rest is infrastructure that consumes trained artifacts and tracks their behavior over time.
