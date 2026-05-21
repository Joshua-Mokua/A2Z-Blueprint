# A2Z MIS 360 — CHANGELOG v5.96

**v5.96 Twenty-Sixth Integration Batch — Customer Value Segments (#66)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — first clean-first-try after v5.95 broke the streak)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🏛️ THIRD SEGMENTATION LENS COMPLETES.** RFM (v5.90) + CLV (v5.95) + Customer Value (v5.96) — three independent, complementary segmentation views. Cumulative: **45 of 116 standards integrated.** Twenty-sixth integration batch.

---

## Strategic milestone — third segmentation lens

After v5.90 RFM (transaction-pattern-based) and v5.95 CLV (balance × yield × NPV-based), v5.96 adds a third lens distinct from both:

| Lens | Engine | Primitive | Output |
|---|---|---|---|
| **v5.90 RFM** | customer_segmentation | transactions (R/F/M) | 11 RFM segments (CHAMPIONS, LOST, etc.) |
| **v5.95 CLV** | customer_lifetime_value | balances × product yields × NPV | 4 profitability segments (HIGH_VALUE, etc.) |
| **v5.96 Customer Value** ⭐ | customer_value_segments | annual contribution + retention | **288 cells**: 6 segments × 4 tiers × 4 tenure × 3 activity |

The three lenses are **independent and complementary**:
- A high-frequency low-balance retail customer: CHAMPIONS (RFM) + LOW (CLV) + BRONZE/MASS (v5.96)
- A low-frequency high-balance HNW customer: HIBERNATING (RFM) + HIGH_VALUE (CLV) + PLATINUM/HNW (v5.96)

Production deployment can compose into a unified score; engine doesn't provide this directly but caller can compose.

---

## Why 288 cells matters

v5.96's segmentation grid is **far more granular** than the other two lenses:

| Segmentation | Cells | Use case |
|---|---|---|
| v5.90 RFM | 11 | Behavioral campaign targeting |
| v5.95 CLV | 4 | Top-line value tiering |
| **v5.96 Customer Value** | **288** | **Granular targeting** (e.g. "PLATINUM+HNW+ESTABLISHED+ACTIVE → top-of-pyramid retention" vs "BRONZE+MASS+NEW+DORMANT → onboarding broke down") |

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.96 wires **Standard #66 Customer Value Segments** (`customer_value_segments.py`) — banking-archetype × tier-band × tenure × activity-status segmentation + retention-rate-perpetuity CLV calculator.

---

## What was modified

### `pages/34_customer360.py` — 6th sub-tab + 5 inner tabs (G4-strict pattern)
**2600 → 3116 lines (+516)**

**Top-level tabs UNCHANGED at 7** (G4 limit). Tab[4] Segment Analytics's `_seg_sub_tabs` **expanded from 5 to 6** (G4-strict respected ≤7):

| # | Sub-tab | Status |
|---|---|---|
| 0-3 | Aggregation / RFM / Value Tiers / Lifecycle | unchanged from v5.90 |
| 4 | Engine Reference | unchanged from v5.90 |
| **5** | **🏛️ Customer Value Segments (#66)** | **NEW** |

Per **G4-strict lesson from v5.95**, the new sub-tab uses "1 sub-tab + 5 inner tabs" pattern (also ≤7):

### 🏷️ Tier Classifier (inner tab)

User inputs annual contribution + None test toggle for Rule 6.

Engine returns one of: PLATINUM 💎 / GOLD 🥇 / SILVER 🥈 / BRONZE 🥉 / **None** (Rule 6 — negative or None input).

Boundaries from `SEGMENT_TIER_BANDS_KES`:
- PLATINUM ≥ KES 1,000,000
- GOLD ≥ KES 250,000
- SILVER ≥ KES 50,000
- BRONZE ≥ KES 0

### 📅 Tenure & Activity (inner tab)

Two parallel classifications:

**Tenure bands** (years_open):
- NEW < 1y · DEVELOPING < 3y · ESTABLISHED < 7y · LOYAL ≥ 7y

**Activity status** (days_since_last_txn):
- ACTIVE < 90d · DORMANT < 180d · ATTRITED ≥ 180d

**Combined high-risk pattern detection**:
- LOYAL + ATTRITED → 🚨 highest-cost churn pattern
- NEW + DORMANT → ⚠ onboarding broke down
- ESTABLISHED/LOYAL + ACTIVE → ✅ healthy long-term relationship

### 💰 CLV Calculator — perpetuity-with-attrition (inner tab)

User inputs:
- annual_contribution + expected_tenure + retention_rate + discount_rate

Engine returns perpetuity-with-attrition CLV (distinct from v5.95's NPV-with-fixed-margin).

Optional **retention sensitivity sweep** 60-95% with line chart:

| Retention | CLV (KES) |
|---|---|
| 60% | 209K |
| 70% | 254K |
| 80% | 320K |
| 85% | 365K |
| 90% | 420K |
| 95% | 490K |

**2.3x range** — surfaces retention as the most leveraged CLV assumption.

### 📊 Segment Aggregate (inner tab)

Synthetic 30-100 customer portfolio across all 6 banking archetypes (deterministic seed=42, distribution: 50% MASS / 20% AFFLUENT / 10% HNW / 10% SME / 8% CORPORATE / 2% GOVERNMENT).

Engine returns per-segment n + total_contribution + avg_contribution.

**Concentration insight**: when GOVERNMENT + HNW ≥ 50% of total contribution → top-of-pyramid risk warning.

### 🌳 Engine Reference (inner tab)

5 reference tables:
- 6 customer segments (banking archetypes)
- 4 tier bands (with byte-for-byte KES boundaries)
- 4 tenure bands (with year ranges)
- 3 activity statuses (with day thresholds)
- 5 engine methods (all STATIC)

Plus **3-lens comparison table**: RFM v5.90 / CLV v5.95 / Customer Value v5.96 with primitive + output dimensions.

### Engine file — UNCHANGED
`utils/customer_value_segments.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED

---

## 5 engine paths verified across boundary cases

**`segment_classification`** — all tier boundaries:

| Contribution (KES) | Tier |
|---|---|
| 999,999,999 | PLATINUM |
| 1,000,000 | PLATINUM |
| 999,999 | GOLD |
| 250,000 | GOLD |
| 249,999 | SILVER |
| 50,000 | SILVER |
| 49,999 | BRONZE |
| 0 | BRONZE |
| -1 (negative) | **None** (Rule 6) |
| None | **None** (Rule 6) |

**`tenure_band`** — all year boundaries correct (exclusive upper):
- 0.99y → NEW
- 1.0y → DEVELOPING
- 2.99y → DEVELOPING
- 3.0y → ESTABLISHED
- 6.99y → ESTABLISHED
- 7.0y → LOYAL

**`activity_status`** — all day boundaries:
- 89d → ACTIVE
- 90d → DORMANT
- 179d → DORMANT
- 180d → ATTRITED

**`clv`** — valid + missing:
- 100K/10y/85%/15% → 365K (computed=True)
- Missing inputs → computed=False, reason=invalid_contribution_or_tenure

**`segment_profitability_aggregate`** — all 6 segments + Rule 6:
- Empty segments correctly return n=0 with avg=None

**Engine logic confirmed**: 4 tier boundaries + 4 tenure boundaries + 3 activity boundaries + perpetuity CLV + 6-segment aggregate all working. Rule 6 transparency on None inputs and empty segments.

---

## Critical engine API specifics documented

These were verified during build (12 findings):

1. **`CustomerValueEngine` has 5 STATIC class methods** — `segment_classification`, `tenure_band`, `activity_status`, `clv`, `segment_profitability_aggregate`. No instance state.

2. **🆕 `segment_classification` returns None for negative or None contribution** (NOT BRONZE) — important Rule 6 gotcha; pages mistakenly assuming non-None will accidentally treat None as BRONZE.

3. **`ClvInputs` requires `customer_id` only** but `clv` returns `computed=False` with `reason=invalid_contribution_or_tenure` if `annual_contribution_kes` or `expected_tenure_years` missing.

4. **🆕 6 CUSTOMER_SEGMENTS are banking archetypes**: MASS / AFFLUENT / HNW / SME / CORPORATE / GOVERNMENT — distinct from v5.90 RFM (11 segments) and v5.95 CLV (4 profitability tiers).

5. **🆕 4 SEGMENT_TIERS with byte-for-byte boundaries** from `SEGMENT_TIER_BANDS_KES`: PLATINUM ≥ 1,000,000 / GOLD ≥ 250,000 / SILVER ≥ 50,000 / BRONZE ≥ 0.

6. **🆕 4 TENURE_BANDS with byte-for-byte year ranges** from `TENURE_BAND_YEARS`: NEW (0-1) / DEVELOPING (1-3) / ESTABLISHED (3-7) / LOYAL (7-999); upper bound is exclusive — exactly-1y is DEVELOPING, exactly-3y is ESTABLISHED.

7. **🆕 3 ACTIVITY_STATUSES with day thresholds**: ACTIVE < 90d / DORMANT 90-179d / ATTRITED ≥ 180d — consistent with v5.90 lifecycle DORMANT_THRESHOLD.

8. **🆕 CLV uses retention-rate-based perpetuity model** distinct from v5.95 CLV's NPV-with-fixed-margin: at 100K annual + 10y tenure + 85% retention + 15% discount → 365K. **Retention sensitivity is highly leveraged** (60%→95% gives 2.3x range).

9. **`segment_profitability_aggregate(customers, segment)` filters list by segment** and returns n + total + avg; **n=0 returns avg=None** (Rule 6) — pages mistakenly dividing by n must check.

10. **🆕 customers list format**: each dict needs `customer_id` + `segment` + `annual_contribution_kes` keys — engine ignores other fields. Production can pass full customer records.

11. **CLV is highly sensitive to retention rate** in this engine (vs v5.95 where horizon dominates) — different model design: v5.96's perpetuity-with-attrition treats retention as a per-period survival probability, compounding dramatically.

12. **Three segmentation lenses are independent**: RFM (v5.90) + CLV (v5.95) + Customer Value (v5.96) use different primitives. **Production may want a unified composite score** combining all three; engine doesn't provide this but caller can compose.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "CustomerValue #66: tier_classify contribution=350000 → GOLD")
audit_log("IFRS_ENGINE_USED", uname, "CustomerValue #66: tenure+activity tenure=2.5y → DEVELOPING, days=45 → ACTIVE")
audit_log("IFRS_ENGINE_USED", uname, "CustomerValue #66: clv DEMO_CVS_001 annual=100000 tenure=10 retention=85 computed=True")
audit_log("IFRS_ENGINE_USED", uname, "CustomerValue #66: segment_aggregate portfolio=30 total=2500000")
```

---

## ✅ Clean-first-try restored after v5.95 streak break

Audit clean on first attempt — **first clean-first-try after v5.95 broke the 20-batch streak**. G4-strict pattern from v5.95 lesson absorbed:

> Both top-level tabs AND sub-tab groups capped at ≤7. Use **"1 sub-tab + N inner tabs"** for depth integrations.

v5.96 followed this pattern: 6 sub-tabs at top level (≤7) + 5 inner tabs in the new sub-tab (≤7). Counter restarts at 1.

---

## Honesty discipline visualised

- **Three segmentation lenses comparison** explicit in Engine Reference table
- **All boundary thresholds** byte-for-byte from engine constants
- **Retention sensitivity 2.3x range** — surfaces retention as most leveraged assumption
- **Rule 6 None handling** — Tier Classifier surfaces None input with explanatory error
- **Rule 6 empty segment** — Segment Aggregate surfaces n=0 with avg=None
- **Rule 6 missing CLV inputs** — surfaces computed=False with reason
- **High-risk pattern detection** — LOYAL+ATTRITED, NEW+DORMANT combinations
- **Concentration insight** — top-of-pyramid risk warning when GOVERNMENT+HNW ≥50%
- **Three-lens independence** documented — production may want composite scoring layer
- Every engine call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G66 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.95 pages — unchanged
- The other 6 top-level tabs in `34_customer360.py` — completely untouched
- The 5 existing _seg_sub_tabs (Aggregation / RFM / Value Tiers / Lifecycle / Engine Reference) from v5.90 — unchanged
- The 7 clv_sub_tabs from v5.75/v5.92/v5.95 — unchanged
- The `customer_intelligence.json` data store — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.95

| | v5.95 | v5.96 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **44** | **45** ⭐ (+1) |
| Audit gates | 103/103 (after retry) | 103/103 (**clean first try**) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 15 | **15** (re-enhances 34_customer360.py) |
| Lines added across pages this batch | +452 (customer360 v5.95) | +516 (customer360 v5.96) |
| **34_customer360.py total lines** | 2600 | **3116** (largest non-people page) |
| Clean-first-try streak | broken at 20 | **restored to 1** |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 6-scenario engine call simulation. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **NEW 6th sub-tab containing 5 inner tabs**. The page now has the **most layered structure in the app**: top-level tab[4] → _seg_sub_tabs[5] → _cvs_inner[0..4].

2. **45 of 116 integrated** — 71 standards remain library-only.

3. **All inner tabs use synthetic / user-entered data** — Tier Classifier uses user input, Tenure & Activity uses user input, CLV Calculator uses user input + retention sweep, Segment Aggregate uses deterministic random portfolio (seed=42 for reproducibility). Production deployment would feed via 3 DI-ready data sources: customer master (segment + annual_contribution_kes + opened_date for tenure + last_txn_date for activity), CBS query for annual contribution computation, retention rate from churn engine v5.91.

4. **🆕 CLV retention model is highly sensitive (2.3x range over 60-95%)** — production deployment should ground retention rate in actual churn data from v5.91, not aspirational targets. **Bank policy on retention assumption must precede production deployment**.

5. **🆕 6 banking archetypes are HARD-CODED** — adding new archetypes (e.g. "PRIVATE_BANKING" splitting from HNW, or "INSTITUTIONAL" from CORPORATE/GOVERNMENT) requires engine code change.

6. **🆕 4 tier thresholds are HARD-CODED** at 1M/250K/50K/0 — production in different markets/currencies needs different boundaries. Kenya context: PLATINUM ≥ KES 1M annual contribution is reasonable; GOLD ≥ KES 250K likely matches MASS_AFFLUENT segment from v5.90.

7. **No CLV time-series support** — engine returns single-snapshot perpetuity NPV. Multi-period scenarios ("customer's CLV trajectory if retention improves from 80% to 90%") require multiple invocations + caller-side composition.

8. **🆕 Three segmentation lenses are NOT unified** — v5.90 + v5.95 + v5.96 use different primitives. **Production deployment may want a composite scorecard** (e.g. "unified tier = max(RFM_tier, CLV_tier, customer_value_tier)" or weighted combination). Engine doesn't provide this; caller can compose.

9. **🆕 Activity threshold inconsistency** — DORMANT_THRESHOLD=90d (v5.96) matches v5.90 lifecycle but **differs from v5.91 churn's NO_TXN_THRESHOLD=60d**. Production deployment should align thresholds across engines (or document explicitly: 60d=churn-flag, 90d=lifecycle-DORMANT, 90d=value-segment-DORMANT).

10. **🆕 Segment Aggregate uses deterministic random distribution** (seed=42, 50%/20%/10%/10%/8%/2% across 6 segments) — production deployment should use real customer master distribution which may differ dramatically (Kenya retail bank likely 80%+ MASS, <0.1% GOVERNMENT).

11. **No support for cross-segment migration analysis** — engine doesn't track segment changes over time. "Customer A moved from MASS to AFFLUENT in Q3" requires session-history persistence + caller-side delta computation.

12. **🆕 ClvInputs allows None retention_rate_pct or discount_rate_pct** — engine uses defaults (DEFAULT_DISCOUNT_RATE_PCT=15) when discount missing, but **retention is not defaulted** (returns computed=False without retention_rate_pct). This is intentional design — there's no "reasonable default" for retention (varies dramatically by segment/market).

---

## Strategic narrative — three-lens segmentation surface

Customer 360's tab[4] Segment Analytics now offers **three independent segmentation lenses**:

| Lens | Sub-tab(s) | Engine | Best for |
|---|---|---|---|
| RFM | sub-tabs 1-3 (RFM/Value Tiers/Lifecycle) | customer_segmentation | Behavioral campaign targeting |
| (Customer 360's tab[5] CLV) | (different tab) | customer_lifetime_value | Top-line value tiering |
| **Customer Value Segments** | **sub-tab 5** | **customer_value_segments** | **Granular targeting (288 cells)** |

The page now offers analysts the full segmentation toolkit — they can choose the lens that matches the analytical question:
- "Who's most engaged?" → RFM
- "Who's most valuable long-term?" → CLV
- "What banking archetype + tier + tenure + activity is this customer?" → Customer Value Segments

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Compensation Equity depth | compensation_equity | Likely features beyond v5.79 (percentile-based pay equity, gender pay gap stats) |
| (2) | Employee Engagement depth | employee_engagement | Likely features beyond v5.79 (eNPS, theme analysis) |
| (3) | More depth batches | various | Review v5.71-v5.85 for engine surfaces not exposed |
| (4) | Composite scoring layer | NEW | Combines v5.90 + v5.95 + v5.96 lenses (would require engine code change) |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With third segmentation lens integrated, recommend **(1) Compensation Equity depth** for v5.97 — would extend HR axis with engine-level depth.

---

**Cumulative tally:** 116 standards delivered, **45 integrated into UI via 3 dedicated pages + 15 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🏛️ **Third segmentation lens** (Customer Value Segments #66 — 288-cell archetype × tier × tenure × activity grid + perpetuity-with-attrition CLV).

✅ **G4-strict pattern from v5.95 lesson confirmed working** — 6 sub-tabs + 5 inner tabs both ≤7, audit clean on first attempt.
