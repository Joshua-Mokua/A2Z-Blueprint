# Changelog — v10.440 HR Rescue Arc Batch 3: Wire #18 (Efficiency) + #19 (Wellness)

**Date:** 2026-05-14
**Phase:** HR Rescue Arc — Batch 3 of 6 (engine wiring, round 2)
**Audit:** G326 added (cumulative 326 gates)
**Tests:** 19/19 PASSED in `test_v10440_hr_wire_efficiency_wellness.py`
**Combined regression:** 288 v10.4xx tests PASSED (269 prior + 19 new)
**Verifier:** 817 → **820** (+3 v10.440 checks)
**G162 baseline:** 4022 (133 consecutive zero-drift batches)
**Master prompt:** v4.82 → v4.83 (lockstep — 84 consecutive batches)

**🎯 HR HEALTH: 61.7% → 69.2%** (engine wiring 50% → 75% — all 4 closed-standards engines now wired).
**360 harmony 100% preserved. BSC rescue 100% preserved. Standards wiring 78.8%.**

---

## What this batch executed

Per v10.436 audit: 4 of 6 closed-standards HR engines unwired. v10.438 wired #14 + #17. v10.440 finishes the closed-standards wiring with #18 + #19:

### Wire #18: `efficiency` (EfficiencyEngine) → `43_pip.py`

**New tab "⚡ Efficiency Insights"** added to PIP. PIP existed for performance improvement; the missing piece was data-driven diagnosis of WHERE to improve.

The flow:
1. Pick a period (current month, last month, current quarter)
2. HR/Admin can select any staff (defaults to PIP staff); regular users see self
3. "Calculate efficiency" calls `EfficiencyEngine.calculate_efficiency_scores(staff, period)`
4. Returns per-KPI personal efficiency (per minute) + vs-peer ratio
5. Table shows each KPI with status indicator:
   - 🟢 Above peers (ratio > 1.0)
   - 🟡 Near peers (0.8 - 1.0)
   - 🔴 Below peers (< 0.8)
6. **Below-peer KPIs flagged as candidates for PIP improvement targets** — the connective tissue PIP was missing
7. Method & traceability metadata available in expander

### Wire #19: `wellness` (WellnessEngine) → `2_people.py`

**New top-level section "🌿 Wellness"** with 3 sub-tabs. WellnessEngine was the most ethically-sensitive engine in the codebase — it computes burnout risk from work signals, with deliberate guardrails. Wiring it required preserving every guardrail:

#### Sub-tab 0 — 🙋 My wellness check
- Self-service: user runs `assess_burnout_risk(self_code)` on demand
- Shows risk_level (🟢 low / 🟡 moderate / 🔴 high), risk_score, contributing signals, recommendations
- **Opt-out explicitly documented**: `wellness_monitoring_disabled: true` on user record returns `{}` — explained as "a feature, not a bug"

#### Sub-tab 1 — 👀 Team alerts (manager)
- Calls `list_alerts_for_manager(mgr_code)` → list of direct-report alerts
- Table shows: staff, risk level, score, triggered date, primary signal
- **Warning banner**: "These alerts are not diagnoses. Have a supportive conversation; consider workload rebalancing; route to HR if patterns persist."

#### Sub-tab 2 — ℹ️ How this works
- **Transparency by design**. Documents all 4 signals:
  1. Escalation frequency (8+ alerts/30d)
  2. Stale micro-tasks (5+ older than 14d)
  3. Declining trajectory (3+ consecutive decreases)
  4. Pace deficit (recent achievement below baseline)
- Risk level thresholds documented
- **All G30 ethical safeguards spelled out:**
  - Never produces medical/emotional speculation
  - Forbidden words listed: `depressed`, `burnt out`, `stress disorder`, `mental health`, `anxiety` — verified absent in WellnessEngine output
  - Opt-out respected
  - High-risk alerts route to manager (escalation)
  - Recommendations focus on workload/process, not personal traits

## File changes

| File | Before | After |
|---|---|---|
| `pages/43_pip.py` | 135 LOC, 4 tabs | **244 LOC, 5 tabs** |
| `pages/2_people.py` | 3,902 LOC, 5 sections | **4,034 LOC, 6 sections** |

## HR engines wiring — final state for closed standards

| Engine | Std | Wired into | Status |
|---|---|---|---|
| `peer_learning` | #14 | `42_lms.py` | ✅ v10.438 |
| `coaching_intelligence` | #15 | `2_people.py` | ✅ pre-existing |
| `predictive_performance` | #16 | `2_people.py` | ✅ pre-existing |
| `gamification` | #17 | `2_people.py` | ✅ v10.438 |
| `efficiency` | #18 | `43_pip.py` | **✅ v10.440** |
| `wellness` | #19 | `2_people.py` | **✅ v10.440** |
| `staff_onboarding_engine` | v10.434 | — | needs NEW page (v10.441) |
| `staff_exit_engine` | v10.435 | — | needs NEW page (v10.441) |

**All 6 closed standards (#14-#19) are now wired into user-facing pages.** Only the 2 v10.434/v10.435 engines remain — and those need NEW pages, not wiring into existing ones.

## Verified outcome

| Metric | v10.439 | v10.440 |
|---|---|---|
| Audit gates | 325 | **326** |
| v10.4xx tests | 269 | **288** (+19) |
| Verifier | 817 | **820** (+3) |
| Lockstep batches | 83 | **84** consecutive |
| G162 baseline | 4022 (132) | 4022 (**133** zero-drift) |
| **HR engine wiring** | 50% (4/8) | **75%** (6/8) |
| **HR overall health** | 61.7% | **69.2%** ↑ |
| Standards wiring | 78.8% | **78.8%** ✓ |
| 360 harmony | 100% | **100%** ✓ |
| BSC rescue | 100% | **100%** ✓ |

## 10 honest acknowledgements

1. **Efficiency Insights is the connective tissue PIP was missing.** PIP staff needed objective data on where to improve. Now the page identifies below-peer KPIs as concrete improvement targets.

2. **WellnessEngine has unusual care built in.** G30 audit gate verifies forbidden words absent. The page preserves every guardrail explicitly — not buried in code, surfaced in the UI.

3. **Self-service first, manager second.** Wellness My-check tab comes first so staff can run on themselves. Manager view second. "How this works" third for transparency.

4. **The opt-out is the most important feature.** `wellness_monitoring_disabled` on user record returns `{}` from the engine, and the UI explains this is a feature. Without that, this would feel like surveillance.

5. **HR engine wiring jumped 50% → 75% from one batch.** Two engines wired = +25 percentage points on that dimension. Same arithmetic as v10.438.

6. **HR overall health +7.5 points** (61.7% → 69.2%). Each engine wiring delivers roughly +3.5 to overall health.

7. **All 6 closed-standards engines wired.** Std #14, #15, #16, #17, #18, #19 are all now user-visible somewhere. The 7-year-old build-and-forget pattern is broken for these engines.

8. **No engine builds.** Both engines existed (462 + 609 LOC). Pure UI wiring, same pattern as v10.438.

9. **No regressions.** 360 harmony 100%, BSC rescue 100%, standards wiring 78.8% all preserved.

10. **v10.441 is structurally different.** Building NEW pages for staff_onboarding + staff_exit is more work than wiring into existing pages. But pattern stays: read engine API, render with `st.tabs`, add admin controls, gate by role.

## Roadmap update

| Batch | Concern | Status |
|---|---|---|
| ~~v10.424–v10.439~~ | BSC + 360 + HR diagnostic + relocation + wire #14+#17 + system diag | **DONE** |
| ~~**v10.440**~~ | **HR Rescue: Wire #18 + #19** | **DONE (69.2%)** |
| **v10.441** | HR Rescue: Build staff onboarding + exit pages | **Next** |
| v10.442 | HR Rescue: FastAPI endpoints for 6 HR engines | |
| v10.443 | HR Rescue: PostgreSQL scaffold | |
| v10.444+ | Systemwide rescue per G325 priorities (reconciliation #1) | |

## On your end

1. Close Streamlit · extract `a2z_v10440_patch.zip` on v10.439 (overwrite all)
2. `python scripts/verify_local_state.py` → expect **820/820**
3. **Open Streamlit → People → Performance Improvement → ⚡ Efficiency Insights** — pick a period, see your per-KPI efficiency
4. **Open Streamlit → People → 🌿 Wellness** — run your own wellness check; managers see team alerts; read "How this works" for the ethical model
5. **Open Streamlit → Admin → BSC Health → HR Section Health Audit** — confirm:
   - Engine wiring: **75%** (was 50%)
   - HR Health: **69.2%** (was 61.7%)
   - Rescue priorities: 3 → 2 (build NEW pages + API endpoints + PostgreSQL remaining)
6. Tell me **"continue"** → v10.441 = build `pages/79_staff_onboarding.py` + `pages/80_staff_exit.py` from v10.434/v10.435 engines

Closed standards #14-#19 are all wired. Six of eight HR engines live in the UI. The body's rescue is well underway. Tell me **"continue"** for v10.441.
