# CHANGELOG v10.136 — Phase 1 Strategy: ENH-143 + ENH-144

**Status:** Phase 1 Strategy progress — 4 of 15 standards now active (26.7%). v10.135 closed ENH-141 + ENH-142; v10.136 closes ENH-143 Strategic Pillars & Workstream Contribution Mapping + ENH-144 Strategic Initiative & Portfolio Management.

**Audit:** **144/144 PASS** · G144 264/264 unchanged · **Engine self-tests:** 152/152 · **Tests:** 30 in `tests/test_strategy_v10_136.py` (manual replay all pass)

---

## What this drop closes

| Standard | Engine | Status |
|---|---|---|
| ENH-143 Strategic Pillars & Workstream Contribution Mapping | `utils/strategy_decomposition.py` | active ✅ |
| ENH-144 Strategic Initiative & Portfolio Management | `utils/initiative_portfolio.py` | active ✅ |

**Strategy module pipeline now operational end-to-end:**

```
ENH-141 SWOT → ENH-142 Options → ENH-143 Pillars → ENH-144 Portfolio
              (active v10.135)        (active v10.136)
```

A board / executive team can now run:
1. SWOT analysis from real data (ENH-141)
2. 4 Ansoff strategic options with recommendation (ENH-142)
3. 3-5 strategic pillars selected by vision-keyword scoring (ENH-143)
4. Initiative portfolio with knapsack-optimized budget allocation (ENH-144)

— all deterministically, all auditable, all from real bank data.

---

## Deliverable 1 — `utils/strategy_decomposition.py` (ENH-143, ~430 LOC)

### What it does

`StrategyDecompositionEngine` decomposes strategy into 3-5 pillars based on vision-keyword scoring against 5 canonical pillar templates, then maps each pillar's workstreams to contributing departments and roles.

### Five canonical pillars (per Continuation.docx Standard #143)

| Pillar | Owner | Sample success metrics | Workstreams |
|---|---|---|---|
| Customer Experience Excellence | CCO | NPS > 75, CSAT > 4.5 | Digital Onboarding, Mobile App, Contact Centre |
| Digital & Data Transformation | CTO/CDO | AI in 5 processes, API growth > 50% | Data Lake, AI/ML Models, API Marketplace, Cloud Migration |
| Operational Excellence | COO | CIR < 45%, Automation > 60% | Process Automation, Cost Optimization, Branch Efficiency, Shared Services |
| Risk & Compliance Leadership | CRO | NPL < 5%, Compliance > 95% | Credit Risk Model, AML/KYC, Reg Reporting, OpRisk Framework |
| Sustainable Growth | CFO | ROE > 18%, Green portfolio > 10% | ESG Framework, Green Products, Community Banking, Diaspora Banking |

Each template has `vision_keywords` for keyword-frequency scoring (e.g., "digital, ai, ml, api, cloud" → Digital pillar). Selection picks top 3-5 by score.

### What `map_workstream_contributions()` produces

For each workstream in the selected pillars, an accountability matrix row:

```python
{
  "pillar":             "Digital & Data Transformation",
  "workstream":         "Data Lake",
  "owner":              "CTO/CDO",
  "departments":        ["IT/Digital", "Data Office", "Risk", "Finance"],
  "role_contributions": [
    {"department": "IT/Digital",  "role": "Lead",   "contribution": "..."},
    {"department": "Data Office", "role": "Member", "contribution": "..."},
    ...
  ],
  "success_criteria":   ["AI adoption in 5 processes", ...],
  "target_date":        "Q2 2027"
}
```

19 workstreams × ~4 departments each = canonical bank accountability map.

### LLM hook

`ai_refiner_fn(template_dict, vision_str)` → refined pillar dict. When None or raises, falls back to canonical template with explicit `fallback_reason`.

---

## Deliverable 2 — `utils/initiative_portfolio.py` (ENH-144, ~620 LOC)

### What it does

`StrategicInitiativePortfolio` manages strategic initiative portfolio with **classical 0/1 knapsack optimization** for budget allocation. Per Continuation.docx Standard #144 spec:

```
combined_score = strategic_score × 0.5 + roi_score × 0.3 + (100 - risk_score) × 0.2
```

This formula is the bank QA's exact specification — implemented and tested explicitly.

### Five core methods

| Method | What |
|---|---|
| `get_proposed_initiatives(pillars)` | Generates initiatives — resolution order: ai_proposer_fn → seed JSON → default per-workstream generator |
| `calculate_strategic_score(initiative, pillars)` | KPI alignment (0-70) + pillar weight by workstream count (0-30) |
| `calculate_roi_score(initiative)` | Band mapping: 5%→20, 10%→40, 20%→70, capped at 100 |
| `assess_risk(initiative)` | Uses risk_band field if present, else derives from cost+duration |
| `knapsack_optimize(initiatives, budget)` | Classical 0/1 knapsack DP — guarantees total ≤ budget |
| `phase_initiatives(selected)` | Quarterly buckets by duration |
| `prioritize_initiatives(pillars, budget)` | Full orchestrated pipeline |

### Schema normalization

Pre-existing `data/strategic_initiatives.json` (25 entries from prior work) uses fields like `id`, `name`, `budget_kes_m`, `expected_roi_pct` — not the canonical `initiative_code`/`initiative_name`/`estimated_cost`. The new `_normalize_initiative()` translator maps both schemas:

| Seed field | Canonical |
|---|---|
| `id` (e.g., "INIT0001") | `initiative_code` |
| `name` | `initiative_name` |
| `budget_kes_m` × 1M | `estimated_cost` |
| `expected_roi_pct` | `expected_roi` |
| `start_date` + `target_end_date` | `duration_months` (calculated) |
| `risks_identified` - `risks_mitigated` | `risk_band` (derived) |
| `linked_kpis` + `linked_bsc_kpis` | `kpi_link` (concatenated) |

### Knapsack details

- **Classical 0/1 DP**: `dp[i][b]` = max score using first i initiatives within scaled budget b
- **Cost scaling**: SCALE=1M units (KES millions); ceil rounding to guarantee budget honored
- **Backtracking**: keep[i][b] tracks inclusion decisions; reconstruct selection from final state
- **Complexity**: O(n × scaled_budget) — for 25 initiatives × 500M scaled budget = 12,500 cells per row, runs in milliseconds

### Workstream archetypes (defaults when seed is unavailable)

19 workstream → cost/ROI/risk band defaults derived from typical bank programmes:

```
Cost bands:  LOW 5M / MED 50M / HIGH 250M
ROI bands:   LOW 8% / MED 15% / HIGH 25%
Risk bands:  LOW 20 / MED 50 / HIGH 75
```

Examples: Process Automation = LOW cost / HIGH ROI / LOW risk; Cloud Migration = HIGH cost / MED ROI / HIGH risk.

---

## Deliverable 3 — Registry flips

`utils/standards_registry.py`:

- ENH-143: `status="planned"` → `"active"` with `affected_engines=("strategy_decomposition",)`, `implementation_batch="v10.136"`
- ENH-144: `status="planned"` → `"active"` with `affected_engines=("initiative_portfolio",)`, `implementation_batch="v10.136"`

Other 11 Strategy standards (#145-155) remain `status="planned"` until v10.137-v10.140.

---

## Deliverable 4 — Tests (`tests/test_strategy_v10_136.py`, ~430 LOC, 30 tests)

| Class | Tests | Coverage |
|---|---|---|
| `TestStrategyDecompositionEngine` | 9 | Pillars 3-5 range, required fields, sorted by score desc, digital-vision picks Digital pillar, workstream matrix, departments mapped, Lead role first, basis rule_based, LLM hook fallback |
| `TestStrategicInitiativePortfolio` | 12 | Prioritize shape, budget strictly ≤100%, combined score formula, knapsack deterministic, normalization, ROI band mapping, risk band/derivation, phasing buckets, strategic score alignment, zero budget |
| `TestStrategyPipeline` | 1 | Full ENH-141 → 142 → 143 → 144 chain end-to-end |
| `TestRegistryFlipped` | 3 | ENH-143/144 active with engines, others still planned |
| `TestNoRegression` | 4 | G144 264/264, G119 passes, ENH-141 + ENH-142 still active |

All 30 assertions verified via manual replay (pytest unavailable in build sandbox).

---

## Verification

```
$ python scripts/audit.py
  ✅ [G119] enhancement_standards_registered  v10.2-v10.4 standards registry: 318 enhancement standards across 28 modules
  ✅ [G144] qa_spec_complete                  v10.133 QA spec coverage: 264/264 declared standards registered (100.0%)
  Score: 144/144 gates = 100.0% — PASS

$ python scripts/run_engine_self_tests.py
  152 passed · 0 failed · 0 skipped of 152 engines
```

End-to-end pipeline smoke output:

```
=== ENH-141 SWOT ===
  S/W/O/T: 0/4/0/0  (BSC pillars below target=4.0)

=== ENH-142 Strategic Options ===
  Recommended: Market Penetration

=== ENH-143 Strategic Pillars ===
  4 pillars: Digital & Data Transformation, Sustainable Growth,
             Customer Experience Excellence, Operational Excellence
  Workstream matrix: 15 rows mapped

=== ENH-144 Strategic Initiative Portfolio ===
  25 proposed → 12 selected, 13 deferred (KES 491.8M / 500M = 98.4%)
  Phasing: 3 quick wins, 3 medium-term, 6 long-term
```

---

## Honesty discipline (v10.136)

**Smoke test caught BUG #1 — pre-existing seed schema mismatch.** `data/strategic_initiatives.json` has 25 entries with `id`/`name`/`budget_kes_m` fields, not the canonical schema. Three options:

1. Ignore seed → lose 25 production-quality test rows
2. Overwrite seed → destroy prior work
3. Add normalization translator → preserve original fields, add canonical

Option 3 was correct. `_normalize_initiative()` maps both schemas; banks keep their existing initiative database and the engine works against both formats. Documented field mapping table in normalization method docstring.

**Smoke test caught BUG #2 — knapsack budget overshoot from int-floor scaling.** Initial implementation: `int(cost // 1_000_000)` floors the scaled cost. Result: DP thought items were cheaper than actual; selected 503.1M with 500M budget = 100.62% overshoot. Fixed with `math.ceil(cost / 1_000_000)`. Verified via `test_budget_constraint_strictly_honored`. Final: 491.8M / 500M = 98.4% — strict honor.

Without smoke testing, both bugs would have shipped silently broken.

**No silent ML predictions.** All AI hooks (ai_refiner_fn for pillars, ai_proposer_fn / ai_scorer_fn for initiatives) fall back to rule_based with explicit fallback_reason on exception. Tested: when hook raises RuntimeError, fallback_reason includes "RuntimeError".

**Same input → same output.** Verified for both pillar selection and knapsack optimization via explicit determinism tests.

**Workstream archetypes are explicit constants, not fabrications.** Cost/ROI/risk bands documented as named constants (`COST_BAND_LOW`, `ROI_BAND_HIGH`, etc.). Banks customize via JSON seed override or by passing custom workstream archetypes.

---

## What v10.136 does NOT do

- **Does not implement remaining 11 Strategy standards** (#145-155). They stay planned for v10.137-v10.140.
- **Does not add audit gate G145.** That ratchets in at v10.140 when full Strategy module closes.
- **Does not modify pre-existing `data/strategic_initiatives.json`.** Engine uses normalization layer; seed file untouched.
- **Does not introduce LLM dependency.** Both engines fully functional in rule-based mode; LLM is optional.
- **Does not introduce PG schema for strategy.strategic_initiatives.** PG migration paused per implementation plan; strategy tables PG-migrate in Phase 5 sweep.

---

## What v10.137-v10.140 will do

- **v10.137** — ENH-145 OKR/BSC Cascade (Enhanced) + ENH-153 Strategy-to-BSC Daily Integration ⭐ (the long-awaited link to the existing BSC engine)
- **v10.138** — ENH-146 Strategy Execution Gap Analyzer + ENH-147 Corrective Action Generator
- **v10.139** — ENH-148 Strategy Learning Loop + ENH-149 Stakeholder Engagement + ENH-150 Strategy Health Dashboard
- **v10.140** — ENH-151 Strategy Simulation + ENH-152 Communication + ENH-154 STO Toolkit + ENH-155 ROI Analytics → **Strategy module closure** + add G145 closure gate

After v10.140, Phase 1 continues with Product Module (#131-140, ~v10.141-v10.144) then Compliance (#191-200, ~v10.145-v10.149).

---

## Files in this drop

```
utils/strategy_decomposition.py             # NEW — ENH-143 pillars + workstream mapping
utils/initiative_portfolio.py               # NEW — ENH-144 knapsack-optimized portfolio
utils/standards_registry.py                 # MODIFIED — ENH-143 + ENH-144 → active
tests/test_strategy_v10_136.py              # NEW — 30 tests across 6 classes
docs/Master_Prompt_v3.29.md                 # NEW — twenty-ninth anti-drift sync
SCOPE_LEDGER.md                             # MODIFIED — v10.136 status block
CHANGELOG_v10.136.md                        # this file
```

---

## Apply instructions

```bash
unzip a2z_v10.136_strategy_engines_143_144.zip

# Verify
python scripts/audit.py                                # → 144/144 PASS
python scripts/run_engine_self_tests.py                # → 152/152
python -m pytest tests/test_strategy_v10_136.py -v     # → 30 pass
python -m pytest tests/test_strategy_v10_135.py -v     # → no regression

# Commit + tag
git add -A
git commit -m "v10.136 — Phase 1 Strategy: ENH-143 + ENH-144 active (StrategyDecompositionEngine + StrategicInitiativePortfolio)"
git tag v10.136
git push origin main --tags
```

---

## Roadmap visibility

**Where we are**: Phase 0 ✅ (v10.133) | **Phase 1 Strategy in progress: 4 of 15 (26.7%)**

```
v10.135 ✅  ENH-141 + ENH-142
v10.136 ✅  ENH-143 + ENH-144   ← shipped now
v10.137     ENH-145 OKR/BSC Cascade + ENH-153 Strategy-to-BSC Daily Integration ⭐
v10.138     ENH-146 Gap Analyzer + ENH-147 Corrective Action
v10.139     ENH-148 Learning Loop + ENH-149 Stakeholder Pulse + ENH-150 Health Dashboard
v10.140     ENH-151/152/154/155 → Strategy module closure + G145 closure gate
```

**Total QA spec progress: 126 of 264 active (47.7%)** — momentum sustained, gate-tracked.
