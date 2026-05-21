# A2Z MIS 360 — CHANGELOG v5.93

**v5.93 Twenty-Third Integration Batch — Coaching Intelligence (#11)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 19th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🤝 HR AXIS COMPLETE.** Retrospective (v5.79) + Forward-looking (v5.84) + Action-oriented (v5.93) all integrated. Cumulative: **42 of 116 standards integrated.** Twenty-third integration batch.

---

## Strategic milestone — HR axis complete

After v5.79 added retrospective HR analytics and v5.84 added forward-looking HR planning, v5.93 closes the loop with action-oriented coaching support:

| Layer | Standards | Integrated in | Coverage |
|---|---|---|---|
| **Retrospective** | #63 Compensation Equity + #64 Engagement + #20+#21 Predictive Performance | v5.79 | What happened |
| **Forward-looking** | Workforce planning + capacity analytics | v5.84 | What should happen |
| **Action-oriented** | **#11 Coaching Intelligence** | **v5.93** ⭐ | **How to make it happen** |

The full HR axis turns insights → planning → conversation:
- **Section 0 Insights** (v5.79+v5.84): analytical view of workforce
- **Section 3 Discipline & Dev** (v5.93): action-oriented manager tooling

Section 3 now contains the full **Manager-tooling stack**:
- ⚖️ Disciplinary (negative correction)
- 📋 PIP management (formal improvement)
- 🎯 Diligence scores (objective assessment)
- **🤝 Coaching Intelligence (positive development)** ⭐

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.93 wires **Standard #11 Coaching Intelligence** (`coaching_intelligence.py`) — generates structured 1:1 coaching scripts from staff signals.

---

## What was modified

### `pages/2_people.py` — Section 3 sub-tab expansion + new coaching sub-tab
**2286 → 2806 lines (+520)**

**Top-level sections UNCHANGED at 4** (well under G4 limit). **Section 3 sub-tabs expanded from 3 to 4**:

| # | Sub-tab | Status |
|---|---|---|
| 0 | ⚖️ Disciplinary | unchanged |
| 1 | 📋 PIP management | unchanged |
| 2 | 🎯 Diligence scores | unchanged |
| **3** | **🤝 Coaching Intelligence (#11)** | **NEW** |

The new sub-tab itself contains 3 inner tabs (deepest nesting in app: Section → sub-tab → inner tab):

### 🤝 Generate Coaching Script (inner tab)

Interactive — user inputs:
- Manager code, staff code, meeting date
- 5 signal counts: KPIs behind / KPIs exceeded / nudges / skill gaps / microtasks

Engine builds 7 DI callbacks from inputs and returns coaching script with:
- **Header banner** showing staff name / role / unit
- **📋 Meeting Agenda** (numbered list, 3-5 items)
- **💬 Talking Points** (bulleted list, 1-8 items, Q-style quoted prompts)
- **✅ Recommended Actions** (numbered list, 1-5 items)
- **Signals used** metrics columns (5 sources)
- Expandable engine metadata viewer

### 🎯 Demo Scenario Builder (inner tab)

6 pre-configured scenarios:
1. High performer (mostly exceeded KPIs)
2. Underperformer (multiple behind KPIs + nudges)
3. Development focus (skill gaps + learning cards)
4. Compliance pressure (microtasks + nudges)
5. Authorization refused (not direct report) — surfaces engine's `{}` return
6. Unknown staff (Rule 6) — surfaces engine's `{}` return per Rule 6

Each shows agenda+talking+actions count metrics + full content + signals_used.

### 🌳 Engine Reference (inner tab)

3 reference tables:

**Output structure constraints:**

| Section | Min | Max | Purpose |
|---|---|---|---|
| 📋 Meeting Agenda | 3 | 5 | Structured talking framework |
| 💬 Talking Points | 1 | 8 | Q-style prompts surfacing signals |
| ✅ Recommended Actions | 1 | 5 | Concrete next steps |

**7 DI callbacks** with returns + default source.

**Authorization model + Rule 6 transparency captions.**

### Engine file — UNCHANGED
`utils/coaching_intelligence.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 1 engine path verified end-to-end (used 7+ times per session)

**`generate_coaching_script` — 4 representative scenarios:**

| Scenario | Agenda | Talking | Actions |
|---|---|---|---|
| **Underperformer (3 KPIs / 1 nudge / 1 skill gap / 1 microtask / 1 learning)** | **5** | **5** | **3** |
| High performer (2 exceeded KPIs only) | 3 | 2 | 1 |
| Authorization refusal | — | — | — (returns `{}`) |
| Unknown staff (Rule 6) | — | — | — (returns `{}`) |

**Signal richness adapts output volume**: more signals → more agenda/talking/actions, within engine bounds (3-5 / 1-8 / 1-5).

**Engine logic confirmed**: 7 DI callbacks orchestrated correctly. Authorization enforced (returns `{}` if manager not direct report). Rule 6 transparency (returns `{}` if staff unknown). Output adapts to signal richness.

---

## Critical engine API specifics documented

These were verified during build (12 findings):

1. **`CoachingIntelligence` is an INSTANCE class** with **7 DI callbacks** (is_direct_report_fn, staff_lookup_fn, kpi_status_fn, nudges_fn, growth_plan_fn, microtasks_fn, learning_cards_fn) — second-most DI-heavy engine after Customer Profitability's 8.

2. **`generate_coaching_script(manager_code, staff_code, today=None)` is the ONLY public method** — narrow API surface, rich orchestration internally.

3. **🆕 Engine returns `{}` for failed authorization** (manager not direct report) — caller must check before accessing keys. **Hierarchical access control** prevents managers coaching outside their reporting chain.

4. **🆕 Engine returns `{}` for unknown staff** (staff_lookup returns None) per Rule 6 — production must ensure staff register is current.

5. **`CoachingScript` dataclass has 7 fields** but engine returns dict with 4 sections + meta dict (NOT the dataclass directly). Top-level keys: `meeting_agenda` + `talking_points` + `recommended_actions` + `meta`. `signals_used` is in `meta.signals_used`.

6. **🆕 `growth_plan_fn` returns dict with `skill_gaps` as list of DICTS** (not list of strings) — each skill_gap dict has `skill` + `current` + `required` keys. **Passing strings causes AttributeError** — documented gotcha discovered during smoke testing.

7. **Output structure constraints**: agenda 3-5 items, talking_points 1-8 items, recommended_actions 1-5 items. Bound byte-for-byte from `DEFAULT_*_MIN/MAX` constants. Engine adapts output volume to signal richness within these bounds.

8. **🆕 Talking points use Q-style quoted prompts** — engine wraps signals in conversational question format (e.g. *"On nps_score you're at 70% of target — what are the biggest blockers right now?"*). Designed for managers to read aloud or paraphrase rather than as bullet points to memorize.

9. **`signals_used` dict has 5 standard keys**: `kpi_status_rows`, `active_nudges`, `growth_plan_present` (1 if dict, 0 if not), `active_microtasks`, `learning_cards`. Caller can detect data gaps (e.g. `growth_plan_present=0` means HR hasn't built plan yet).

10. **🆕 Engine prioritizes signals by category** — typical agenda flow: review wins (exceeded KPIs) → discuss gaps (behind KPIs) → development focus (skill gaps) → confirm tasks (microtasks) → action plan. Helps manager balance positive recognition with constructive feedback.

11. **Engine has NO ML/LLM dependency** — fully deterministic Python orchestration of structured signals into structured output. Production deployment can extend with LLM-based natural language polish but core engine is deterministic per Rule 7.

12. **🆕 `meta.signals_used` values are STRINGS** in the engine output despite being counts — caller may want to coerce with `int()` for arithmetic.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "Coaching #11: script MGR001→STAFF001 agenda=5 talking=5 actions=3")
audit_log("IFRS_ENGINE_USED", uname, "Coaching #11: scenario 'Underperformer (multiple behi'")
```

---

## ✅ Nineteenth clean-first-try batch in a row

Audit clean on first attempt (after v5.74 → v5.92). G3 + G4 lessons embedded.

---

## Honesty discipline visualised

- **All output structure constraints** explicit (3-5 / 1-8 / 1-5) bound byte-for-byte from engine
- **Authorization model surfaced** — refused scenarios in Demo Scenario Builder with explanatory error
- **Rule 6 transparency** — unknown staff scenario shows engine's `{}` return semantics
- **`signals_used` displayed** — caller can detect data gaps (growth_plan_present=0)
- **Skill_gaps schema gotcha documented** — must be list of DICTS not strings
- **Q-style talking points** — engine designed for conversation, not memorization
- **Engine integration with v5.79 + v5.84 documented** — completes HR axis triplet
- Every engine call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G11 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.92 pages — unchanged
- The 4 top-level sections in `2_people.py` (Insights / Records / Leave / Discipline & Dev) — unchanged
- The 3 existing sub-tabs in Section 3 (Disciplinary / PIP management / Diligence scores) — unchanged
- All v5.79 + v5.84 work in Section 0 — unchanged
- `app.py` — unchanged

---

## Comparison vs v5.92

| | v5.92 | v5.93 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **41** | **42** ⭐ (+1) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 15 | **15** (re-enhances 2_people.py from v5.79 + v5.84) |
| Lines added across pages this batch | +409 (customer360 v5.92) | +520 (people v5.93) |
| **2_people.py total lines** | 2286 | **2806** (still longest page in app) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and engine call simulation across 4 scenarios. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **NEW 4-sub-tab structure under Section 3** with the new sub-tab containing 3 inner tabs. **The page now has the deepest nesting in the app**: top-level Section 3 → sub[3] Coaching Intelligence → inner ci_sub_tabs[0/1/2].

2. **42 of 116 integrated** — 74 standards remain library-only.

3. **All sub-tabs use synthetic signal data** — Generate Coaching Script uses user-entered counts that get translated into synthetic signal lists, Demo Scenario Builder uses 6 pre-configured signal mixes. Production deployment would feed via 7 DI callbacks connecting to:
   - `target_cascade.json` (is_direct_report_fn)
   - `staff_register.xlsx` (staff_lookup_fn)
   - bsc_engine actuals (kpi_status_fn)
   - `data/nudges.json` (nudges_fn)
   - `data/growth_plans.json` (growth_plan_fn)
   - `data/microtasks.json` (microtasks_fn)
   - `data/learning_cards.json` (learning_cards_fn)

4. **🆕 Engine has 7 DI callbacks** — production deployment must wire all 7 carefully because missing/incorrect callbacks fail silently (skill_gaps schema mismatch returns AttributeError, not a clean error). **Production callers should validate callback returns at the integration layer.**

5. **No support for batch script generation** — engine processes one (manager, staff) pair at a time. Generating scripts for a manager's full team requires repeated invocations. Production deployment should add a batch wrapper for scheduling.

6. **🆕 Authorization is binary direct-report check** — engine doesn't support skip-level coaching (e.g. Director coaching their direct's direct). **In reality, skip-level conversations are valuable**; production deployment may want to expand authorization model to include 2-level cascade matches.

7. **🆕 No ML/LLM polish** — engine produces deterministic structured output with template Q-style prompts. Production deployment that wants natural-language smoothing would layer an LLM on top of the structured output (post-processing only — engine remains deterministic per Rule 7).

8. **No multi-language support** — output is English only. Production deployment in non-English markets would need template translation.

9. **Talking points are limited to KPIs + skill gaps + microtasks** — doesn't surface other potentially useful signals (peer feedback, customer complaints, recent training completion). Production deployment can extend by adding callbacks but core engine catalog is fixed.

10. **🆕 No support for coaching session history** — engine generates a fresh script each time without context from previous 1:1s. *"Last meeting we agreed X — how's that going?"* requires session-history persistence. Production deployment with persistent meeting notes could surface this.

11. **`signals_used` doesn't differentiate signal QUALITY** — manager seeing kpi_status_rows=4 doesn't know if those 4 KPIs are high-confidence or low-confidence. Production deployment may want to surface confidence intervals or data freshness.

12. **🆕 Engine doesn't model coaching outcomes** — generated script is single-direction (engine→manager). **Outcomes (did the meeting happen? were actions completed?) require separate tracking.** Production deployment with action-tracking workflow can close the loop; current scope is script generation only.

---

## Strategic narrative — HR axis complete

People page (`pages/2_people.py`) now has the full HR triplet integrated:

| Section | Layer | Coverage | Integrated |
|---|---|---|---|
| **Section 0 Insights** | **Retrospective + Forward-looking** | Compensation Equity + Engagement + Predictive Performance + Workforce Planning | v5.79 + v5.84 |
| **Section 3 Discipline & Dev** | **Action-oriented** | Disciplinary + PIP + Diligence + **Coaching Intelligence** | (existing) + **v5.93** ⭐ |

The HR axis answers all three temporal questions:
- **Retrospective (v5.79)**: What happened? — *Compensation equity gaps, engagement trends, performance attainment*
- **Forward-looking (v5.84)**: What should happen? — *Workforce planning, capacity gaps, succession*
- **Action-oriented (v5.93)**: How to make it happen? — *Structured 1:1 coaching scripts*

**Page is now 2806 lines — still the longest page in the app** (Customer 360 at 2148 is second).

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Allocation Optimizer | allocation_optimizer | Pivot to NEW axis (resource allocation) — capital/people deployment optimization |
| (2) | Customer Lifetime Value depth | customer_lifetime_value | Engine-level depth beyond v5.75 |
| (3) | Customer Value Segments | customer_value_segments | Alternative segmentation lens |
| (4) | Compensation Equity depth | compensation_equity | If engine has features beyond v5.79 |
| (5) | Employee Engagement depth | employee_engagement | If engine has features beyond v5.79 |
| (6) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With HR axis complete and customer-centric quartet complete, recommend **(1) Allocation Optimizer** for v5.94 — would extend the platform to **resource allocation** which is a different functional axis (capital/people deployment optimization) complementing the customer + HR axes already built.

---

**Cumulative tally:** 116 standards delivered, **42 integrated into UI via 3 dedicated pages + 15 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🤝 **HR axis complete** (Retrospective v5.79 + Forward-looking v5.84 + Action-oriented v5.93).
