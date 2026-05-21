# A2Z MIS 360 — v5.53 CHANGELOG

**Release:** v5.53 (April 2026)
**Theme:** Volume Six — Dormancy Intelligence + EDMS
**Score:** 52/52 audit gates passing 100%

---

## What shipped

**2 new standards (#41–#42)** completing Volume Six. This is a smaller batch by count but mixes 4 risk categories — Cat B (status engine), Cat D (prediction with Rule 7), Cat A (schema), Cat C (workflow with legal-hold honesty).

| # | Standard | Risk cat | Lines | Self-tests |
|---|---|---|---|---|
| 41 | Dormancy Intelligence | B (status) + D (prediction) | 430 | 14/14 |
| 42 | EDMS Intelligence | A (schema) + C (workflow) | 470 | 18/18 |

**Total:** ~900 LOC of new analytical/governance code, 32 self-test cases, all green.

## New audit gates (G51–G52)

| Gate | Type | Coverage |
|---|---|---|
| G51 dormancy_intelligence_correct | combined inline + artifact-handoff (≥99%) | CBK thresholds 300/365/730 + Rule 7 (no_model fallback) + 10/10 = 100% on classification fixtures DI001-DI010 |
| G52 edms_engine_correct | inline programmatic | 4 classifications + 8 retention defaults + 3 deletion methods + LEGAL HOLD ALWAYS WINS (Rule 4) |

## Tampering tests verified

- **G51 CBK threshold tampered** (365 → 400) → caught with 2 violations
- **G51 SPEC_DEVIATION_NOTE tampered** → caught with 1 violation
- **G51 classification fixture tampered** → harness fails at 9/10=90%, gate flags accuracy drop
- **G52 CONTRACT retention tampered** (15 → 5 years) → caught with 1 violation
- **G52 legal_hold check tampered** (logic bypassed) → caught with **3 violations** — most important detection: a code-level bug that would let legal-held documents be modified is detectable

## Architectural milestones

### 1. Second Rule 7 application (Cat D scaffolding pattern stabilized)

Standard #41's `predict_dormancy()` is the SECOND application of v6's **Rule 7 — No silent ML predictions**, after #48 in v5.52. Same pattern, same audit-gate verification:

- ML hook (`model_loader_fn`) injectable but disabled by default
- When no model: `ml_score=None` + `reason="no_ml_model_loaded"` + rule-based score surfaced separately (NEVER silently substituted)
- Rule-based fallback is DETERMINISTIC (5-component sum: balance_decline + tx_gap + digital_adoption + product_type + age_segment)
- ML failure path falls back AND surfaces error reason
- `SPEC_DEVIATION_NOTE` preserved byte-for-byte

**Significance:** the pattern is now stable. ~10 more Cat D standards through #120 will follow the same structure (#65 candidate AI, #71 AI HR, #90 lead scoring, #94 AI marketing, #98 AI agent assist, #100 chatbot, #106 win probability, etc.).

### 2. Legal hold honesty rule (Rule 4 strengthened)

Standard #42's EDMS engine establishes the strongest version of Rule 4 (default-strict) yet:

- **Legal hold ALWAYS wins** — no override mode exists. There is no `force_delete` flag, no admin-bypass, no "exceptional circumstances" override.
- Legal hold blocks MODIFY + DELETE regardless of caller role
- Legal hold permits VIEW (read-only access preserved — accessibility for legitimate review)
- Legal-held documents are SKIPPED by the daily retention-expiry job, regardless of how far past `retention_until` they are
- The audit gate verifies this by attempting to apply expiry on a legal-held document past retention — if any modification occurs, the gate fails

This is exactly the kind of rule that needs to survive future "feature requests" and code reviews. The audit gate will catch any drift.

### 3. CBK regulation byte-for-byte

The dormancy thresholds (300/365/730 days) come from CBK regulation. The audit gate verifies:
- 364 days → WARNING (not yet DORMANT)
- 365 days → DORMANT (strict ≥)
- 729 days → DORMANT
- 730 days → RESTRICTED (strict ≥)

A tampering test changing `DORMANCY_THRESHOLD_DAYS` from 365 to 400 was caught with 2 violations.

## Honesty rules (7 total — no new ones)

The 7 honesty rules established through v5.52 all continue. Rule 7 was the new addition in v5.52; v5.53's #41 prediction is its second application. No new rules were added in v5.53 — the existing rules cover the work cleanly:

1. Standard #11 — Financial Accounting Honesty
2. Portfolio-level inheritance (now extended to product dimension via v5.52 #47)
3. Alert suppression on mixed-mode periods
4. **Default-strict downstream submission — strengthened in v5.53 #42 (legal hold ALWAYS wins, no override)**
5. Stale-extract guard for data integration
6. **No privilege-escalation defaults — applied in v5.53 #41 (missing date → ACTIVE with note, not DORMANT)**
7. **No silent ML predictions — second application in v5.53 #41 (predict_dormancy)**

## Spec deviations (still 4 cumulative)

No new deviations in v5.53. The Cat D scaffolding for #41 prediction follows the same pattern as #48 and is covered by deviation #3 (Rule 7 / Cat D scaffolding pattern formalised in v5.52).

## Test count

- v5.52: 31 test files / 794 test functions
- **v5.53: 32 test files / 826 test functions** (+32 in `tests/test_volume_six_batch.py`)

## Files added

```
utils/dormancy_intelligence.py                       (Standard #41)
utils/edms.py                                        (Standard #42)
tests/test_volume_six_batch.py                       (32 test functions)
tests/fixtures/dormancy_classification_scenarios.json (10 fixtures DI001-DI010)
dormancy_classification_results.json                  (G51 artifact, 10/10 = 100%)
```

## Files modified

```
scripts/audit.py             — added G51, G52 gate functions and registrations
Master_Prompt_v3.md          — bumped v5.52→v5.53, added v5.53 closure entry,
                                added G51-G52 gate descriptions
```

## What's next

Per v6 spec §5 recommended sequence:

```
Volume Eight (#49-#52) — Execute Enhancement
```

4 standards extending the existing Execute module (BSC initiatives tracking):
- #49 Initiative Impact Automation Engine (Cat B/C)
- #50 Stage-Gate Governance Engine (Cat C)
- #51 Initiative Dependency & Risk Intelligence (Cat B)
- #52 Initiative Resource Intelligence (Cat B)

All Cat B/C — no new Rule 7 applications. Estimated 1 session, gates G53-G55, target 55/55 score.

---

**v5.53 status: 2 new standards (#41-#42), 2 new gates (G51-G52), 52/52 = 100%. Volume Six complete. Volume Eight up next.**
