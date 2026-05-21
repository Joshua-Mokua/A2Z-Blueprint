# CHANGELOG — v10.185

**Drop:** v10.185
**Standard:** ENH-161 — Employee Wellbeing & Burnout Prevention Integration
**Module:** Resource Optimization
**Status:** active

---

## Summary

Sixth drop of the Resource Optimization arc and the most privacy-sensitive
engine in the platform to date. Sits **above** the existing per-individual
`utils.wellness.WellnessEngine` (Standard #19) and composes it with ENH-160
utilization signals to surface **team-level** early warning signals while
protecting individual employee privacy.

The engine never names individuals in its output, suppresses any team cell
with fewer than 5 assessable members, treats opt-outs as absent (not as a
risk category), and never auto-pushes referrals or interventions.

This is operational risk triage, not clinical assessment. The deferral of
clinical validation is named explicitly in `board_summary()`.

---

## Files added

- `tests/test_wellbeing_integration_v10_185.py` — 41 tests across 12 classes

## Files modified

- `utils/standards_registry.py` — ENH-161 set to `status='active'`,
  `affected_engines=('wellbeing_integration',)`,
  `implementation_batch='v10.185'`
- `pages/7_admin.py` — Tier 32 Resource Optimization Suite gains a sixth
  entry under `wellbeing_integration`

## Files already in place from prior session

- `utils/wellbeing_integration.py` — engine (~390 LOC) was pre-built before
  this session's compaction; this drop closes the loop with tests, audit
  verification, changelog, and packaging.

## Audit gates

No new gates this drop (closure-tier gates G156/G157 land at v10.190 with the
arc closure ceremony). Audit holds at **155/155 PASS = 100.0%**.

---

## Privacy posture (the design contract)

Hard rules, all enforced by tests:

1. **No individual names/codes in team-level outputs.** Test
   `TestNoIndividualLeakage.test_to_dict_has_no_staff_codes` flattens
   `TeamSignal.to_dict()` and asserts none of the input staff codes appear.
2. **n < 5 cohort suppression — applied twice.** First on `n_total` (before
   running per-employee assessments at all), then again on `n_assessed`
   (post opt-out). A team that goes from 6 members to 1 assessable after
   opt-outs is suppressed exactly the same as a team of 1.
3. **Opt-out is absent, not a category.** `WellnessEngine.assess_burnout_risk`
   returns `{}` for opted-out individuals; the engine increments `n_optout`
   and does NOT count them toward any risk band.
4. **Unknown risk levels treated as opt-out, not fabricated.** If the
   underlying assessor returns `risk_level: 'Catastrophic'`, the engine
   records that as a non-assessment, not as a new band.
5. **No clinical claims.** Test `TestHonestDeferrals.test_engine_does_not_diagnose`
   asserts `board_summary()` text contains neither "diagnosis" nor "diagnose".

---

## Engine surface

### Inputs

`assess_team_signal(team_code, staff_codes)` — list of staff codes, never
returned as part of the output.

### Composition (optional)

- `wellness_assessor: Callable[[str], Dict]` — required at construction;
  matches `WellnessEngine.assess_burnout_risk` signature
- `utilization_engine` — optional ENH-160 instance; when provided,
  `sustained_utilization_breach` is computed from team-level breach counts.
  Failures inside the utilization engine fall back to `False` (test
  `TestUtilizationComposition.test_util_engine_failure_safe`)

### Outputs

`TeamSignal` — frozen dataclass:
- `team_code` — back to the caller; the only identifier in the output
- `n_total`, `n_assessed`, `n_optout` — counts only
- `band` — `TeamWellbeingBand`: `GREEN` / `AMBER` / `RED`
- `risk_band_counts` — `{Low: int, Moderate: int, High: int}`
- `sustained_utilization_breach` — bool from ENH-160 composition
- `intervention_level` — `MONITOR` / `SOFT_INTERVENTION` /
  `HARD_INTERVENTION` / `EAP_REFERRAL`
- `rationale` — sanitised string; never names individuals
- `data_suppressed` — when `True`, all count fields are zero

### Band logic (codified in tests)

| Condition | Band | Intervention |
|---|---|---|
| All Low | `GREEN` | `MONITOR` |
| ≥1 High or ≥30% High+Moderate | `AMBER` | `SOFT_INTERVENTION` |
| ≥3 High, no breach | `RED` | `HARD_INTERVENTION` |
| ≥3 High AND sustained breach | `RED` | `HARD_INTERVENTION` |
| RED + ≥50% High+Moderate | `RED` | `EAP_REFERRAL` |

### Honest deferrals (declared in `board_summary()`)

1. **CLINICAL_VALIDATION** — operational risk bands only. No validated
   clinical instrument (MBI / Oldenburg / Copenhagen) is integrated. The
   engine is not a screening tool.
2. **SENTIMENT_FEED_NLP** — explicitly out of scope. NLP on emails / chat /
   Slack would raise severe consent and DPA §44 issues. Not on the roadmap.
3. **EAP_INTEGRATION_PUSH** — EAP referrals are output recommendations only.
   Engine does not push to a provider; HR owns the action.
4. **K_ANONYMITY_FORMAL** — n<5 suppression is rule-based; no formal
   k-anonymity guarantee against background-knowledge attacks.

---

## Validation

### Tests

```
PASSED: 41 | FAILED: 0
```

Coverage spans:

- `TestModuleShape` — public API surface (7 tests)
- `TestRegistry` — ENH-161 active and wired (3)
- `TestHubIntegration` — Tier 32 entry present (2)
- `TestSuppressionOnTotalCohort` — n<5 on n_total (4)
- `TestSuppressionOnAssessableCohort` — n<5 post opt-out (3)
- `TestNoIndividualLeakage` — no staff codes in outputs (2)
- `TestBandClassification` — GREEN/AMBER/RED + EAP escalation (5)
- `TestUtilizationComposition` — ENH-160 hookup + safe failure (3)
- `TestMultiTeamSummary` — rollup with suppression (2)
- `TestHonestDeferrals` — all 4 deferrals + non-clinical language (3)
- `TestEngineConstruction` — input validation (2)
- `TestNoRegression` — ENH-156..160 still active (5)

### Audit

```
Score: 155/155 gates = 100.0% — PASS
```

---

## What this unlocks

ENH-162 (What-If Scenario Simulator for Hybrid Scheduling) is the next drop.
It will consume work-mode declarations (ENH-156), forecasts (ENH-157), TSL
targets (ENH-158), balancing recommendations (ENH-159), utilisation bands
(ENH-160), and now wellbeing signals (ENH-161) to let managers run "what if
we shift this team to 3 days remote" simulations against the full operational
picture.

---

## Notes

- Engine is pure Python. No ML, no NLP, no sensors.
- Regulatory basis returned by `board_summary()`: Kenya OSH Act 2007 §6 +
  DPA 2019 §44 (special category — health data) + Internal Mental Health &
  Wellbeing Policy.
- The DPA §44 anchor is the legal reason the n<5 suppression is set high
  rather than at n<3: health-related aggregate data warrants the more
  conservative threshold.
