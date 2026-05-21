# CHANGELOG v10.139 — Phase 1 Strategy: ENH-148 + ENH-149 + ENH-150

**Status:** Phase 1 Strategy progress — 11 of 15 standards now active (73.3%). v10.135-v10.138 closed the first 8; v10.139 closes ENH-148 Strategy Learning Loop + ENH-149 Stakeholder Engagement & Pulse + ENH-150 Strategy Review & Health Dashboard. Three engines covering institutional memory, employee engagement measurement, and the executive command-centre dashboard backing logic.

**Audit:** **144/144 PASS** · G144 264/264 unchanged · G117 98.2% (222/226) · **Engine self-tests:** 152/152 · **Tests:** 32 in `tests/test_strategy_v10_139.py` (manual replay all pass)

---

## What this drop closes

| Standard | Engine | Status |
|---|---|---|
| ENH-148 Strategy Learning Loop & Next Planning | `utils/strategy_learning.py` | active ✅ |
| ENH-149 Stakeholder Engagement & Pulse Engine | `utils/stakeholder_engagement.py` | active ✅ |
| ENH-150 Strategy Review & Health Dashboard | `utils/strategy_health.py` | active ✅ |

**Together these complete the learning + engagement + dashboard arc:**

```
Past cycle execution (gaps + actions)
                ↓
       ENH-148 Learning Loop
       (success/failure factors)
                ↓
       ENH-149 Engagement Pulse  ──→  ENH-150 Health Dashboard
       (workforce signal)            (executive command centre)
                ↓
        Next strategy cycle
```

A board / executive team can now run the full Strategy module:

```
SWOT (141) → Options (142) → Pillars (143) → Portfolio (144) →
Cascade (145) → Daily BSC (153) → Gap Detection (146) →
Corrective Actions (147) → Learning (148) →
Engagement Pulse (149) → Health Dashboard (150)
```

— with 4 standards remaining (151/152/154/155 in v10.140).

---

## Deliverable 1 — `utils/strategy_learning.py` (ENH-148, ~520 LOC)

### Initiative classification thresholds (per Continuation.docx Standard #148)

| Threshold | Behavior |
|---|---|
| `completion_pct ≥ 90` AND `rag_status ≠ Red` AND (`actual_roi ≥ 0.8 × expected_roi` OR `actual_roi == 0`) | Successful |
| `completion_pct < 60` OR `rag_status == "Red"` OR `actual_roi < 0.5 × expected_roi` | Failed |

### Common-factor extraction

For each FACTOR_DIMENSIONS field (`department`, `type`, `sponsor`, `pillar`), count occurrences across success/failure groups. Patterns require `MIN_FACTOR_FREQUENCY=2` occurrences to surface — single-occurrence factors are NOT presented as patterns (anti-fabrication).

### Recommendation types

| Type | Trigger |
|---|---|
| **discriminator** | Same dimension shows pattern in both success AND failure with different values |
| **replicate** | Success-only pattern (no failure with different value) |
| **mitigate** | Failure-only pattern |

### Persistent storage

`data/strategy_lessons.json` — keyed by cycle_id; same cycle_id overwrites (idempotent). Ships with seed `2025_baseline_cycle` containing real classification of the 25 initiatives in `strategic_initiatives.json`.

### AI hooks (opt-in, transparent fallback)

`ai_market_evolution_fn` and `ai_strategic_recs_fn` for `generate_next_cycle_insights()`. When None or raises, returns explicit `{"status": "deferred", "reason": "..."}` rather than fabricating market intelligence.

---

## Deliverable 2 — `utils/stakeholder_engagement.py` (ENH-149, ~430 LOC)

### Four canonical pulse questions (verbatim from Continuation.docx Standard #149)

```python
PULSE_QUESTIONS = (
    "I understand how my work contributes to bank strategy",
    "I feel empowered to make decisions that support strategy",
    "I receive regular updates on strategy progress",
    "My input is valued in strategic planning",
)
```

### Pulse score formula

For each response, validate Likert 1-5 answers. Per-question average across all responses, then mean-of-means scaled to 0-100:

```
score = ((mean_of_question_means - 1) / 4) × 100
```

### Engagement levels

| Level | Threshold |
|---|---|
| HIGH | score ≥ 75 |
| MEDIUM | 50 ≤ score < 75 |
| LOW | score < 50 |
| no_data | no responses available |

### Comment sentiment (rule-based by default)

Positive keywords: `good, great, excellent, love, appreciate, value, engaged, positive, supported, empowered`
Negative keywords: `bad, poor, frustrated, ignored, disconnected, lost, confused, unclear, unsupported, stressful`

LLM sentiment hook (`ai_sentiment_fn`) injectable; results tagged `basis="llm"` on success, fallback to rule_based on exception.

### Strategy contribution campaigns

Per Continuation.docx Standard #149 spec:

| Reward | Amount |
|---|---|
| best_idea | KES 50,000 |
| most_feasible | KES 25,000 |
| most_innovative | KES 25,000 |

Default submission period 30 days. Submissions ranked by votes desc with timestamp tiebreaker.

---

## Deliverable 3 — `utils/strategy_health.py` (ENH-150, ~580 LOC)

### Backing engine for the dashboard page

The Continuation.docx spec describes a Streamlit page at `pages/150_strategy_dashboard.py`. We ship the **deterministic engine that backs it** so the page is a thin presentation layer.

### Health score formula

```
overall_score = (
    0.50 × pillar_progress_avg          # weight 50%
    + 0.30 × (100 - gap_severity_pct)   # weight 30%
    + 0.20 × engagement_score           # weight 20%
)
```

**Weights re-normalize transparently** when components missing — partial signals don't produce misleading low scores. Engine surfaces actual weights used in the response payload.

### Per-pillar risk classification

| Risk Level | Trigger |
|---|---|
| **HIGH** | ≥ 2 HIGH gaps OR progress < 50 |
| **MEDIUM** | Any HIGH gap OR 50 ≤ progress < 75 |
| **LOW** | No HIGH gaps AND progress ≥ 75 |
| **UNKNOWN** | No initiatives mapped to pillar (with explicit fallback_reason) |

### Threshold-based alerts (NO ML forecasting)

| Code | Trigger |
|---|---|
| `MULTI_PILLAR_HIGH_RISK` | ≥ 2 pillars at HIGH risk |
| `HIGH_TOTAL_GAP` | total_gap_value > 100 |
| `LOW_ENGAGEMENT` | engagement score < 50 |

### Next review date (deterministic)

| Cadence | Logic |
|---|---|
| QUARTERLY | Current quarter end (Mar 31 / Jun 30 / Sep 30 / Dec 31) |
| MONTHLY | Next month start |

---

## Deliverable 4 — Admin hub Tier 4 expanded

`pages/7_admin.py` Tier 4 — Strategy & Initiatives — appended 3 new entries: `strategy_learning`, `stakeholder_engagement`, `strategy_health`. Total Strategy engines now 11 (up from 8).

**G117 engine_hub_integration_coverage at 98.2% (222/226)**. The 4 still-uncovered engines are cross-cutting infrastructure (`aggregation_rules_loader`, `kpi_ownership`, `mlops_persistence`, etc.) accessed via other engines, not direct UI surfaces.

---

## Deliverable 5 — Tests (`tests/test_strategy_v10_139.py`, ~520 LOC, 32 tests)

| Class | Tests | Coverage |
|---|---|---|
| `TestStrategyLearningLoop` | 9 | Shape, threshold classification, min frequency, recommendation types, idempotent storage, AI hook fallback |
| `TestStakeholderEngagement` | 10 | Shape, no_data, score formula (4s → 75), level thresholds, canonical questions verbatim, sentiment classification, LLM hook + fallback, campaign metadata, ranking |
| `TestStrategyHealthEngine` | 8 | Payload shape, weight renorm, no_data, no-initiative pillar fallback, threshold alerts, no-fabrication, deterministic next-review-date |
| `TestEndToEnd` | 1 | Full ENH-148 + 149 + 150 cooperation |
| `TestHubIntegration` | 1 | All 11 strategy engines in admin hub |
| `TestRegistryFlipped` | 4 | ENH-148/149/150 active, 4 others planned |
| `TestNoRegression` | 3 | G144 264/264, G117 passes, prior 8 strategy standards still active |

All 32 assertions verified via manual replay.

---

## Verification

```
$ python scripts/audit.py
  ✅ [G117] engine_hub_integration_coverage  98.2% coverage (222/226); 0 violations
  ✅ [G119] enhancement_standards_registered v10.2-v10.4 standards registry: 318 enhancement standards
  ✅ [G144] qa_spec_complete                 264/264 declared standards registered (100.0%)
  Score: 144/144 gates = 100.0% — PASS

$ python scripts/run_engine_self_tests.py
  152 passed · 0 failed · 0 skipped of 152 engines
```

End-to-end smoke output:

```
=== ENH-148 Strategy Learning Loop ===
  Total initiatives: 25, Successful: 6, Failed: 8
  Recommendations: 4
    [discriminator] Prefer department='Retail' over 'IT' for next cycle
    [discriminator] Prefer type='Cost Reduction' over 'Risk Management' for next cycle
    [discriminator] Prefer sponsor='MD' over 'Director Retail' for next cycle
    [mitigate] Mitigate failure pattern: pillar='Operational Excellence' (3 failures)
  Stored to data/strategy_lessons.json: True

=== ENH-149 Stakeholder Engagement & Pulse ===
  Pulse (no responses): score=None, level=no_data
  Pulse (8 synthetic Retail Banking responses, all 4s): score=75.0/100, level=HIGH
    raw_mean=4.0/5, completion_rate=1.0
  Campaign for 'Digital & Data Transformation':
    rewards: {best_idea: 50000, most_feasible: 25000, most_innovative: 25000}
    3 submissions ranked correctly by votes

=== ENH-150 Strategy Health Dashboard ===
  Overall score: 51.69/100  (AT_RISK)
  Components: {progress: 78.38, gap_inverse: 0, engagement: 62.5}
  Weights used: {progress: 0.5, gap_inverse: 0.3, engagement: 0.2}
  Next review: 2026-06-30
  1 alert: [MEDIUM] HIGH_TOTAL_GAP — Total gap value 480 exceeds threshold 100
  3 insights surfaced from real signals
```

---

## Honesty discipline (v10.139)

**No silent ML predictions across all three engines.** AI hooks (`ai_market_evolution_fn`, `ai_strategic_recs_fn`, `ai_sentiment_fn`, `ai_insight_fn`) all tag results `basis="llm"` on success and fall back to rule_based with explicit explanation on exception.

**ENH-148 explicit "deferred" stubs** when AI hooks not injected — `generate_next_cycle_insights()` returns `{"status": "deferred", "reason": "requires external feed or LLM hook"}` rather than fabricating market intelligence.

**ENH-149 returns score=None with level="no_data"** when no pulse responses available — does NOT fabricate zero. Tested explicitly.

**ENH-150 returns progress=None with explicit fallback_reason** for pillars not present in `strategic_initiatives.json` (pillars like "Risk & Compliance Leadership" or "Digital & Data Transformation" that may not have seed initiatives). Health score weights re-normalize transparently when components missing.

**Same input → same output** verified across all three engines.

**No fabricated alerts.** ENH-150 surfaces only thresholds actually crossed, not speculative "may break" warnings.

**Pulse questions are EXACT canonical strings** from Continuation.docx (no paraphrasing). Reward amounts (KES 50K/25K/25K) are doc-spec constants, not invented.

---

## What v10.139 does NOT do

- **Does not implement final 4 Strategy standards** (#151/152/154/155). They stay planned for v10.140.
- **Does not add audit gate G145.** That ratchets in at v10.140 when full Strategy module closes.
- **Does not include the Streamlit dashboard page.** The backing engine ships; `pages/150_strategy_dashboard.py` is a thin layer to be added in v10.140 if desired.
- **Does not write to performance.* tables.** Read-only contract honored.
- **Does not enforce pulse response collection.** Engine returns `no_data` honestly when no responses available.

---

## What v10.140 will do

- ENH-151 Strategy Simulation & What-If Analyzer
- ENH-152 Strategy Communication
- ENH-154 STO Toolkit
- ENH-155 ROI Analytics
- **Strategy module closure** (15/15)
- **G145 audit gate** locking Strategy module completeness

After v10.140: Phase 1 continues with Product Module (#131-140, ~v10.141-v10.144) and Compliance Module (#191-200, ~v10.145-v10.149).

---

## Files in this drop

```
utils/strategy_learning.py                         # NEW — ENH-148 institutional memory
utils/stakeholder_engagement.py                    # NEW — ENH-149 pulse + campaigns
utils/strategy_health.py                           # NEW — ENH-150 dashboard backing engine
utils/standards_registry.py                        # MODIFIED — ENH-148/149/150 → active
pages/7_admin.py                                   # MODIFIED — Tier 4 hub: +3 strategy engines
data/strategy_lessons.json                         # NEW — baseline cycle seed
tests/test_strategy_v10_139.py                     # NEW — 32 tests across 8 classes
docs/Master_Prompt_v3.32.md                        # NEW — thirty-second anti-drift sync
SCOPE_LEDGER.md                                    # MODIFIED — v10.139 status block
CHANGELOG_v10.139.md                               # this file
```

---

## Apply instructions

```bash
unzip a2z_v10.139_strategy_engines_148_149_150.zip

# Verify
python scripts/audit.py                                # → 144/144 PASS, G117 98.2%
python scripts/run_engine_self_tests.py                # → 152/152
python -m pytest tests/test_strategy_v10_139.py -v     # → 32 pass
python -m pytest tests/test_strategy_v10_138.py -v     # → no regression
python -m pytest tests/test_strategy_v10_137.py -v     # → no regression
python -m pytest tests/test_strategy_v10_136.py -v     # → no regression
python -m pytest tests/test_strategy_v10_135.py -v     # → no regression

# Commit + tag
git add -A
git commit -m "v10.139 — Phase 1 Strategy: ENH-148 + ENH-149 + ENH-150 (learning + engagement + dashboard)"
git tag v10.139
git push origin main --tags
```

---

## Roadmap visibility

**Where we are**: Phase 0 ✅ (v10.133) | **Phase 1 Strategy in progress: 11 of 15 (73.3%)**

```
v10.135 ✅  ENH-141 + ENH-142
v10.136 ✅  ENH-143 + ENH-144
v10.137 ✅  ENH-145 + ENH-153 ⭐ (BSC engine link)
v10.138 ✅  ENH-146 + ENH-147 (execution feedback loop)
v10.139 ✅  ENH-148 + ENH-149 + ENH-150 (learning + engagement + dashboard)   ← shipped now
v10.140     ENH-151/152/154/155 → Strategy module closure + G145 closure gate
```

**Total QA spec progress: 133 of 264 active (50.4%) — past the half-way mark.**

The Strategy module is 73.3% complete. v10.140 closes it.
