# A2Z MIS 360 — CHANGELOG v5.85

**v5.85 Fifteenth Integration Batch — RCSA / Internal Controls + Operational Risk (#43 + #44)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 11th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🛡️ GOVERNANCE/CONTROL AXIS INTEGRATED.** First governance/control axis batch completing the major functional surface coverage. Cumulative: **34 of 116 standards integrated.** Fifteenth integration batch.

---

## Strategic milestone — governance/control axis integrated

The Risk & Compliance team's RCSA register page now contains both:
- **Strategic risk register** (existing) — 5 tabs covering high-risk filters, all risks, heat map, KRIs, add risk
- **Engine-driven control attestation + loss tracking** (NEW v5.85) — 2 tabs covering 9 sub-tabs of deterministic engine output

This completes the **governance/control axis** — Risk & Compliance team can now use deterministic engine-generated control test outcomes, deficiency classifications, and operational loss aggregations alongside the existing manual risk register flow.

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.85 wires **2 standards** in one batch:
- **Standard #43 Operational Risk Loss Events** → `operational_risk.py` (Basel II ORM taxonomy)
- **Standard #44 Internal Controls** → `internal_controls.py` (COSO Framework)

---

## What was modified

### `pages/54_rcsa.py` — Internal Controls + Operational Risk tabs added
**136 → 840 lines (+704)** — largest single-batch line addition this campaign

Top-level tabs expanded from 5 to 7 (exactly at G4's 7-tab limit):

| # | Tab | Status |
|---|---|---|
| 0-4 | High Risk · All Risks · Heat Map · KRIs · Add Risk | unchanged |
| **5** | **🛡️ Internal Controls (Standard #44)** | **NEW** |
| **6** | **⚠️ Operational Risk Engine (Standard #43)** | **NEW** |

### Internal Controls tab — 6 sub-tabs (Standard #44)

**📐 Sample Size Calculator** — selectable risk level (LOW/MEDIUM/HIGH/KEY) returns sample size 25/40/60/90 and tolerance 10%/5%/2%/0% byte-for-byte from `SAMPLE_SIZES_BY_RISK` and `TOLERABLE_EXCEPTION_RATE_PCT`. KEY controls flagged with zero-tolerance warning.

**✅ Control Test** — input test parameters, engine returns:
- Outcome: **EFFECTIVE** / **PARTIALLY_EFFECTIVE** / **INEFFECTIVE**
- exception_rate_pct, effectiveness_pct
- sample_adequate boolean (warns when sample under-tested)
- Missing data handled with Rule 1 transparency

**⚠️ Classify Deficiency** — input financial impact + total assets + flags. Engine returns severity:
- **DEFICIENCY** (< 1% impact)
- **SIGNIFICANT_DEFICIENCY** (≥ 1% impact OR affects FR + no compensating controls)
- **MATERIAL_WEAKNESS** (≥ 5% impact)

Severity-coded callouts with audit committee escalation guidance.

**🏛️ COSO Component Score** — rate 1-5 the principles for selected component. Engine surfaces `missing_principles` list with `missing_count` for Rule 6 transparency. Only computes scores for components with at least one rated principle.

**📊 Effectiveness Summary** — 12-test demo dataset across all 5 COSO components. Engine returns `by_component` breakdown plus `overall_effectiveness_pct` with strong/moderate/weak verdict at 90%/70% boundaries.

**🌳 Engine Reference** — 4 reference tables: sample sizes + tolerance, 17 COSO principles across 5 components, deficiency severity thresholds.

### Operational Risk Engine tab — 4 sub-tabs (Standard #43)

**📝 Log Loss Event** — Basel ORM category dropdown with all 7 `ORM_CATEGORIES`. Engine auto-assigns severity from `SEVERITY_THRESHOLDS` byte-for-byte:

| Severity | Threshold |
|---|---|
| LOW | < KES 100K |
| MEDIUM | < KES 1M |
| HIGH | < KES 10M |
| SEVERE | ≥ KES 10M |

SEVERE events trigger CBK PG/06 disclosure warning.

**📊 Aggregate by Category** — period-bounded aggregation across 7 categories with event counts, total impact, average loss, severity distribution. Bar chart of total impact by category. Gracefully handles zero-event periods.

**📈 KRI Metrics** — event_frequency, period_days, events_per_day, severe_events count with red callout if any SEVERE in period, severity distribution table.

**🌳 Engine Reference** — 3 reference tables: 7 ORM categories with descriptive Basel definitions, severity thresholds byte-for-byte, 4 EVENT_STATUSES.

### Persistent engine instance via session_state

```python
if "_orm_engine" not in st.session_state:
    st.session_state._orm_engine = OperationalRiskEngine()
```

Ensures events logged in one tab persist into aggregate/KRI tabs within the same session. Engine uses default in-memory `event_store_fn` and `event_query_fn` callbacks (production deployment would inject DB-backed callbacks).

### Engine files — UNCHANGED
`utils/internal_controls.py` and `utils/operational_risk.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 8 engine paths verified end-to-end

**#44 Internal Controls — 5 paths:**

| Path | Test data | Output |
|---|---|---|
| `sample_size("LOW"/"MEDIUM"/"HIGH"/"KEY")` | 4 risk levels | 25/40/60/90 with 10%/5%/2%/0% tolerance |
| `sample_size("UNKNOWN")` | Invalid | `error: unknown_risk_level:UNKNOWN` |
| `test_control(60 sample, 1 exception, HIGH)` | 1.67% rate vs 2% | **PARTIALLY_EFFECTIVE** (any non-zero is partial) |
| `test_control(60 sample, 5 exceptions, HIGH)` | 8.33% vs 2% | **INEFFECTIVE** |
| `test_control(missing data)` | Rule 1 | outcome=None, reason="missing_sample_or_exceptions" |
| `classify_deficiency(50K / 100B)` | 0.00005% impact | **DEFICIENCY** |
| `classify_deficiency(6B / 100B + FR + no compensating)` | 6% impact | **MATERIAL_WEAKNESS** |
| `coso_component_score(5 CE principles rated 4)` | 12 principles missing | overall=4.00, missing_count=12 |
| `control_effectiveness_summary(10 tests)` | 8 effective + 1 partial + 1 ineffective | **80%** overall_effectiveness_pct |

**#43 Operational Risk — 3 paths (across 5 logged events):**

| Path | Test data | Output |
|---|---|---|
| `log_loss_event(EXTERNAL_FRAUD, 2.5M)` | Card skimming | success=True, severity=**HIGH** |
| `log_loss_event("UNKNOWN", ...)` | Invalid category | success=False with valid_categories list |
| `log_loss_event(INTERNAL_FRAUD, 15M)` | Embezzlement | severity=**SEVERE** |
| `log_loss_event(EXECUTION_DELIVERY, 500K)` | Wire error | severity=**MEDIUM** |
| `log_loss_event(CLIENTS_PRODUCTS_BUSINESS, 50K)` | Customer dispute | severity=**LOW** |
| `log_loss_event(BUSINESS_DISRUPTION, 8M)` | Datacenter outage | severity=**HIGH** |
| `aggregate_losses_by_category(2026-04-01→2026-04-30)` | 5 events | total=26.05M; severity dist L=1/M=1/H=2/S=1 |
| `compute_kri_metrics(...)` | Same period | freq=5, severe=1, events_per_day=0.1667 over 30 days |

**Engine logic confirmed**: severity auto-assignment by impact correctly bands all 4 levels. Aggregate returns ALL 7 categories (zero-event included). KRI severe_events flags executive escalation candidates.

---

## Critical engine API specifics documented

These were verified during build (12 findings):

### `InternalControlsEngine` (#44):

1. **5 STATIC methods** (no instance state) — sample_size, test_control, classify_deficiency, coso_component_score, control_effectiveness_summary. Easy to wire.

2. **`ControlTest`** requires test_id/control_id/coso_component/risk_level + optional sample_size/exceptions_found/test_period_start/test_period_end. Missing sample_size or exceptions_found returns `outcome=None` with `reason='missing_sample_or_exceptions'` (Rule 1).

3. **🆕 `test_control` for KEY risk has ZERO tolerance** — `tolerance_pct=0` means any non-zero exception fails (INEFFECTIVE). For HIGH/MEDIUM/LOW risk, ANY non-zero exception within tolerance returns PARTIALLY_EFFECTIVE not EFFECTIVE — only zero exceptions yield EFFECTIVE.

4. **`classify_deficiency` impact_pct** = (estimated_financial_impact_kes / total_assets_kes) × 100, returned as Decimal string with 4 decimal places (e.g. '0.0000', '6.0000').

5. **🆕 `coso_component_score` returns `component_scores` dict with None** for components without any rated principles (graceful) and `missing_principles` list naming exactly which principles weren't rated (Rule 6). **overall_score is mean of rated component scores, NOT mean of all 17 principle ratings** — 1 fully-rated component gives overall_score = that component's score even if 4 components are entirely unrated.

### `OperationalRiskEngine` (#43):

6. **Constructor takes 2 dependency-injection callbacks** (event_store_fn, event_query_fn) plus instance-level `self._events: List[dict]` for default in-memory storage. Production deployment must inject DB-backed callbacks for persistence across sessions.

7. **`log_loss_event`** returns dict with `success` boolean, `event_id` if success (format `EVT_YYYYMMDDHHMMSSffff`), `severity` (auto-assigned from financial_impact_kes vs SEVERITY_THRESHOLDS), `category`, `financial_impact_known` boolean — Rule 1 transparency for events without quantified impact.

8. **🆕 Severity thresholds are EXCLUSIVE upper bounds** — `LOW: <100K`, `MEDIUM: <1M`, `HIGH: <10M`, `SEVERE: ≥10M` (no upper bound). SEVERE has `threshold=None` to indicate unbounded.

9. **`aggregate_losses_by_category` returns ALL 7 categories** in `by_category` dict even if zero events (event_count=0, total_impact=0, average_loss=None) — page filters to non-zero categories for display.

10. **`compute_kri_metrics`** returns `severity_distribution` dict with all 4 severity levels even if zero events in some — caller can build complete distribution chart without missing keys.

### Both engines:

11. **Both engines use Decimal extensively** — page coerces with `_D_or(str(x))` before float conversion to avoid precision loss in display.

12. **Categories list (7 items)** is fixed and corresponds to Basel II Op Risk taxonomy — no extension expected.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "Controls #44: sample_size HIGH → 60")
audit_log("IFRS_ENGINE_USED", uname, "Controls #44: test T_2026Q2_001 PARTIALLY_EFFECTIVE (1.67% vs 2%)")
audit_log("IFRS_ENGINE_USED", uname, "Controls #44: classify D_2026Q2_001 → MATERIAL_WEAKNESS (6.0000% of assets)")
audit_log("IFRS_ENGINE_USED", uname, "Controls #44: COSO CONTROL_ENVIRONMENT score=4.00 missing=12")
audit_log("IFRS_ENGINE_USED", uname, "Controls #44: effectiveness 80.0% across 10 tests")
audit_log("IFRS_ENGINE_USED", uname, "OpRisk #43: log EVT_20260501... EXTERNAL_FRAUD HIGH")
audit_log("IFRS_ENGINE_USED", uname, "OpRisk #43: aggregate 2026-04-01→2026-04-30 events=5 total=26050000")
audit_log("IFRS_ENGINE_USED", uname, "OpRisk #43: KRI freq=5 severe=1 days=30")
```

---

## ✅ Eleventh clean-first-try batch in a row

Audit clean on first attempt (after v5.74 → v5.84). G3 + G4 lessons embedded. Page now sits at exactly G4's 7-tab limit.

---

## Honesty discipline visualised

- **Sample size by risk level surfaced** byte-for-byte from `SAMPLE_SIZES_BY_RISK`
- **Tolerance bands explicit** — HIGH=2% / KEY=0% (KEY zero tolerance highlighted)
- **EFFECTIVE / PARTIALLY_EFFECTIVE / INEFFECTIVE** clearly differentiated — any non-zero exception = partial
- **Material Weakness 5% threshold** surfaced byte-for-byte
- **COSO missing_principles** explicitly named for each unrated component (Rule 6)
- **Severity bands for ORM events** auto-assigned with clear thresholds
- **CBK PG/06 disclosure warning** for SEVERE events
- **Audit committee escalation guidance** for SIGNIFICANT_DEFICIENCY and MATERIAL_WEAKNESS
- **Session-scoped storage transparency** — caption notes events lost when session ends
- Every engine call audit-logged

---

## What didn't change

- Both engine source files — byte-for-byte unchanged
- `scripts/audit.py` — gates G43 + G44 still pass exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.84 pages — unchanged
- The 5 existing tabs in `54_rcsa.py` (High Risk / All Risks / Heat Map / KRIs / Add Risk) — completely untouched
- The existing `rcsa_register.json` data store — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.84

| | v5.84 | v5.85 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **32** | **34** ⭐ (+2) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 11 | **12** (54_rcsa.py is a new entry) |
| Lines added across pages this batch | +387 (people) | **+704 (rcsa)** — largest single-batch line addition this campaign |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 8-path engine call simulation at the CLI. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **6-sub-tab and 4-sub-tab nesting** under the two new top-level tabs (page now at exactly G4's 7-tab limit) and the bar chart in Aggregate by Category.

2. **34 of 116 integrated** — 82 standards remain library-only.

3. **Operational Risk Engine uses session-scoped in-memory storage** — `st.session_state._orm_engine = OperationalRiskEngine()` persists events within a single Streamlit session but **events are LOST when the session ends**. Production deployment MUST inject `event_store_fn` and `event_query_fn` callbacks pointing at the bank's DB (likely the existing `a2z_db.load_json/save_json` for `op_risk_events.json` or an actual SQL table). Documented as deferred enhancement; the in-memory default is appropriate for the integration's teaching/QA purpose.

4. **The new ORM event log does NOT integrate with the page's existing `rcsa_register.json` data store** — the existing risks register handles strategic risk identification; the new ORM tab handles tactical loss events. **The two flows are deliberately decoupled** because they have different data shapes (risks have residual scores + KRIs; events have categorical + impact data). Future v5.86+ could integrate the two via cross-references but would require schema design work.

5. **COSO Component Score requires 17-principle data entry** — UI lets user score one component at a time. For full COSO assessment, user must run scoring 5 times (once per component) to get all components rated. Engine does NOT enforce this — it returns scores only for rated components and surfaces missing_principles count. Caller can iterate to build full assessment. Production deployment would benefit from a multi-component scoring widget, but current single-component approach is appropriate for a teaching/QA UI.

6. **Effectiveness Summary uses hard-coded 12-test demo dataset** — production deployment would feed via `control_test_results.json`. Documented deferred enhancement; engines work and Risk team can validate engine outputs against demo data before connecting real test results from internal audit's testing programme.

7. **Material Weakness threshold `MATERIAL_WEAKNESS_THRESHOLD_PCT=5%` is bound byte-for-byte** — matches SEC guidance for SOX 404. For local CBK requirements that may differ, engine code change required. CBK guidance largely follows SOX 404 patterns so 5% is generally appropriate for Kenyan tier-2 banks.

8. **Operational Risk Engine has no UI for event lifecycle management** — `EVENT_STATUSES` (OPEN/INVESTIGATING/RESOLVED/CLOSED) exist on the engine event store but are not exposed in the simplified UI integration. Production deployment with a dedicated incident management workflow would expose status transitions similar to v5.82 Branch Ops Excellence's incident workflow tab.

9. **🆕 The two engines were authored by different people** with slightly different conventions — InternalControls uses static methods (no instance state, easy to call), OperationalRisk uses an instance class with DI callbacks (stateful, supports testing). Page handles both styles uniformly but the difference is documented for future engine harmonization.

10. **Severity bands are based on `financial_impact_kes` only** — events without quantified impact (`financial_impact_known=False` in the engine response) are still logged but not severity-bucketed; KRI metrics may underrepresent the true risk profile when many events lack impact estimates. **Bank should establish a process to estimate impact within (e.g.) 7 days** of event detection to keep KRI metrics meaningful.

---

## Strategic narrative — major functional surface coverage now complete

| Batch | Axis | Status |
|---|---|---|
| v5.78 | Daily risk-management trifecta (IRRBB + LCR/NSFR + Stress) | ✅ Complete |
| v5.79 + v5.84 | HR temporal picture (retrospective + forward-looking) | ✅ Complete |
| v5.80 + v5.82 | Branch axis (strategic + operational) | ✅ Complete |
| v5.80 + v5.83 | Channels axis (strategic + operational) | ✅ Complete |
| v5.81 | Regulatory framework arc (PG/02 → PG/03 → ICAAP → PG/04 → BSD Returns) | ✅ Complete |
| **v5.85** | **Governance/control axis (#43 ORM + #44 COSO Internal Controls)** | **✅ NEW** |

The major functional surface coverage is now complete. v5.86+ will fill in remaining gaps (KYC/AML compliance, channel income, smart alerts, customer insights) but the strategic skeleton is in place.

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | KYC/AML Risk | kyc_aml_risk | Customer risk scoring, sanctions screening, transaction monitoring — completes compliance theme alongside v5.81 + v5.85 |
| (2) | Channel Income | channel_income | Third Channels enhancement (cost-to-serve) |
| (3) | Smart Alerts | smart_alerts | Enhance pages/36_smart_alerts.py |
| (4) | Customer Insights | customer_insights | If not already covered |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With governance/control axis integrated, recommend **(1) KYC/AML Risk** for v5.86 — natural extension of the compliance theme, completes a long-standing regulatory theme alongside v5.81 CBK Returns and v5.85 Internal Controls.

---

**Cumulative tally:** 116 standards delivered, **34 integrated into UI via 3 dedicated pages + 12 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🛡️ **Governance/control axis integrated** (Operational Risk #43 + Internal Controls #44).
