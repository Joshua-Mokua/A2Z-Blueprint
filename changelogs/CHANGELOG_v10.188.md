# CHANGELOG — v10.188

**Drop:** v10.188
**Standard:** ENH-164 — Integrity Culture Score & Benchmarking
**Module:** Resource Optimization
**Status:** active

---

## Summary

Ninth drop of the Resource Optimization arc — and the second
privacy-sensitive engine after ENH-161 Wellbeing. Composes four
operator-supplied indicators into a composite Integrity Culture Score
(ICS) on a 0–100 scale, classifies into four bands, and supports
optional benchmarking against an operator-supplied external score.

The engine refuses to do any of the things that culture-tech vendors
typically promise: no NLP on emails or chat, no keystroke or call-volume
telemetry, no bundled cross-industry benchmark dataset, no automated
survey delivery. Operator collects indicators offline (surveys, audit
reviews, process metrics) and submits aggregates. The engine composes;
it does not sense.

n_respondents < 5 → suppressed, matching the §44 special-category
posture used in ENH-161. Sub-scores are not published when suppressed.

---

## Files added

- `utils/integrity_culture.py` — engine (~340 LOC)
- `tests/test_integrity_culture_v10_188.py` — 56 tests across 14 classes

## Files modified

- `utils/standards_registry.py` — ENH-164 set to `status='active'`,
  `affected_engines=('integrity_culture',)`,
  `implementation_batch='v10.188'`
- `pages/7_admin.py` — Tier 32 Resource Optimization Suite gains a ninth
  entry under `integrity_culture`

## Audit gates

No new gates this drop (closure-tier gates G156/G157 land at v10.190
with the arc closure ceremony). Audit holds at **155/155 PASS = 100.0%**.

---

## Engine surface

### Inputs

`CultureSubmission` (per team-period):
- `team_code`, `period_label` — required, non-empty
- `n_respondents` — required, non-negative
- `transparency_score`, `trust_score`, `sentiment_score`,
  `code_of_conduct_score` — each required, must be in `[0, 100]`
- `external_benchmark_score` — optional, `[0, 100]` if supplied

`CultureWeights` (engine-level):
- `transparency`, `trust`, `sentiment`, `code_of_conduct` — must sum to
  exactly 1.0 (within 1e-6); each non-negative; default 0.25 each

### Validation

Five rejection paths, all tested:
1. Empty `team_code` or `period_label`
2. Negative `n_respondents`
3. Score outside `[0, 100]`
4. Benchmark outside `[0, 100]`
5. Engine construction with weights that don't sum to 1.0

### Privacy posture

`MIN_RESPONDENTS = 5` (matches ENH-161). When `n_respondents < 5`:
- `composite_score` is `None`
- `band` is `None`
- `sub_scores` is `{}` (empty — sub-scores not published)
- `delta_vs_benchmark` is `None`
- `relative_band` is `None`
- `data_suppressed = True`
- `rationale` says "data suppressed — n_respondents < 5"

`weights_used` is still recorded on suppressed records — the operator
can verify what would have been applied.

### Outputs

`CultureScore`:
- `composite_score` — `Σ (sub_score_i × weight_i)`
- `band` — `STRONG (≥80) / DEVELOPING (60–80) / AT_RISK (40–60) /
  CRITICAL (<40)`. Boundary points belong to the higher band.
- `sub_scores` — flat dict of all four indicator values
- `weights_used` — flat dict of weights applied (for audit)
- `delta_vs_benchmark` — `composite − external_benchmark` (None if no
  benchmark)
- `relative_band` — `LEADING (delta ≥ +5) / ON_PAR (|delta| < 5) /
  LAGGING (delta ≤ -5)`

### Honest deferrals (declared in `board_summary()`)

1. **NLP_TEXT_ANALYSIS** — explicitly out of scope. No parsing of
   emails, chat, Slack, or call transcripts. This is not on the
   roadmap; it raises severe consent and §44 issues.
2. **REAL_TIME_BEHAVIORAL_TELEMETRY** — no keystroke, email-volume,
   call-volume, or video-presence monitoring.
3. **CROSS_INDUSTRY_BENCHMARK_DATA** — no external benchmark dataset
   bundled. Operator supplies the comparator score per submission.
4. **CULTURAL_SURVEY_AUTOMATION** — surveys conducted offline via
   existing HR / communications tooling. The engine ingests aggregate
   results; it does not deliver the surveys.

---

## Validation

### Tests

```
PASSED: 56 | FAILED: 0
```

Coverage spans:

- `TestModuleShape` — public surface (7 tests)
- `TestRegistry` — ENH-164 active and wired (3)
- `TestHubIntegration` — Tier 32 entry + ordering (2)
- `TestCultureWeights` — sum=1.0, negatives, engine-level rejection (4)
- `TestSubmissionValidation` — 6 rejection paths (6)
- `TestSuppression` — n<5, n=5 boundary, no sub-scores when suppressed,
  weights still recorded (5)
- `TestCompositeMath` — equal weights, known composite, custom weights,
  weights_used recorded (4)
- `TestBandClassification` — STRONG / DEVELOPING / AT_RISK / CRITICAL +
  boundary points 40 / 60 / 80 (7)
- `TestBenchmark` — none, leading, lagging, on_par, delta math (5)
- `TestMultiTeam` — counts, distribution, average excludes suppressed (3)
- `TestLatestPerTeam` — latest write wins per team (1)
- `TestHonestDeferrals` — all 4 deferrals + reg basis + non-monitoring
  language (3)
- `TestSerialization` — JSON round-trip, suppressed record serialises (2)
- `TestNoRegression` — ENH-156, 161, 162, 163 still active (4)

### Audit

```
Score: 155/155 gates = 100.0% — PASS
```

---

## What this unlocks

ENH-165 (Executive Resource Optimization Dashboard) is the final
standard before the arc closure ceremony at v10.190 with G156/G157.
That dashboard will compose all 9 prior arc engines into a board-level
read-only summary.

---

## Notes

- Engine is pure Python, deterministic, no dependencies.
- Composite math is a straight weighted average — no normalisation, no
  smoothing, no ML. The operator sees the same number they would compute
  by hand from the inputs.
- `weights_used` is recorded on every score record (suppressed or not)
  so reviewers can verify which weighting scheme was active at the time
  of scoring.
- Regulatory basis: Internal Code of Conduct + Speak-Up / Whistleblower
  Policy + Kenya DPA 2019 §44 (special-category) + BSC People + Internal
  Controls perspective.
