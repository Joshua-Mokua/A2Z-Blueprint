# Changelog — v10.441 HR Rescue Arc Batch 4: Build Staff Onboarding + Exit Pages

**Date:** 2026-05-14
**Phase:** HR Rescue Arc — Batch 4 of 6 (engines without pages → pages built)
**Audit:** G327 added (cumulative 327 gates)
**Tests:** 21/21 PASSED in `test_v10441_build_onboarding_exit_pages.py`
**Combined regression:** 309 v10.4xx tests PASSED (288 prior + 21 new)
**Verifier:** 820 → **826** (+6 v10.441 checks)
**G162 baseline:** 4022 (134 consecutive zero-drift batches)
**Master prompt:** v4.83 → v4.84 (lockstep — 85 consecutive batches)

**🎯 HR HEALTH: 69.2% → 76.2%** (engine wiring 75% → **100%** — all 8 HR engines wired).
**Module placement 100% (0 should-be-but-arent). 360 harmony 100% preserved. BSC rescue 100%.**

---

## What this batch executed

Per v10.436 audit: 2 engines from v10.434/v10.435 existed with no user-facing page. v10.441 builds both.

### NEW `pages/79_staff_onboarding.py` — Staff Onboarding fit-in

Wires `staff_onboarding_engine` (v10.434, 600 LOC) into a 4-tab user page:

| Tab | Engine function | Purpose |
|---|---|---|
| 🆕 Simulate Onboarding | `simulate_onboarding()` | Project a hypothetical hire's BSC before adding. Form with role/unit dropdowns; shows projected BSC rows, weight sum, pillar coverage, score viability |
| 🔍 Validate Record | `validate_new_staff()` | Pre-add field/role/duplicate/manager checks. Form with required + optional fields; surfaces errors + warnings + info |
| 👤 Per-Staff Audit | `audit_staff_completeness()` | Verify any existing staff's full canonical fit across 6 dimensions. Pillar coverage visualization, missing role_kpis listing, issues panel |
| 📊 Bank-Wide Audit | `audit_all_staff_completeness()` | 1,437-staff rollup: 81.8% fully fit, 261 partial, 0 failing, weight invariant 100%, score computable 100% |

Quick header shows: total staff, fully fit %, partial fit, weight invariant %.

### NEW `pages/80_staff_exit.py` — Staff Exit & Succession Planning

Wires `staff_exit_engine` (v10.435, 907 LOC) into a 4-tab user page:

| Tab | Engine function | Purpose |
|---|---|---|
| 🎯 Per-Staff Exit Risk | `audit_exit_risk()` | 5-dimension risk score for any staff. Outgoing cascade, value flow (KES), role peers, pillars at risk, incoming reliance. Auto-flags Critical/High with succession recommendation |
| 🚨 Top Key-Person Risks | `audit_all_exit_risks()` | Bank-wide ranking by composite risk. Slider for top_n (5-50). Shows code, name, role, score, band, drivers |
| 🔄 Redistribution Plan | `simulate_exit()` → 3 strategies | All 3 strategies tested (peer_split / manager_absorb / hold_open) with feasibility %, unassigned value, warnings. Receiver detail for recommended strategy |
| 📊 Bank-Wide Exit Readiness | `audit_all_exit_risks()` | 4 risk band counts (Critical/High/Medium/Low), avg score, top global drivers, critical staff table |

Quick header shows: critical/high/medium counts + avg risk score.

## Manifest registration

Both pages registered under `people_hr` with:
- Onboarding: `module_path=people_hr.onboarding`, icon `🆕`, key `onboarding`
- Exit: `module_path=people_hr.exit`, icon `🚪`, key `exit`
- Both have `require_access` strings matching their module paths

Manifest stamp `_v10441_new_pages` documents what was built.
Backup of pre-batch manifest in `data/_v10441_backups/_manifest.json.before`.

## Engine extension (forward-compat fix)

`audit_module_placement.should_be_in_hr_but_arent` in `hr_section_audit_engine.py` was a hard-coded list in v10.436. After v10.441 it's **dynamic** — detects whether the 2 pages exist and returns `[]` when both are present. The v10.437 placement check still passes (forward-compatible).

## People (HR) section — now 7 pages

```
👥 People (HR)
├ 2_people.py            People (3,783 LOC, 6 sections)
├ 42_lms.py              Learning Management (199 LOC, 7 tabs)
├ 43_pip.py              Performance Improvement (244 LOC, 5 tabs)
├ 58_workforce.py        Workforce Planning (86 LOC, 1 tab) ⚠️ STUB
├ 60_disciplinary.py     Disciplinary Register (110 LOC, 1 tab) ⚠️ STUB
├ 79_staff_onboarding.py Staff Onboarding (NEW, 230+ LOC, 4 tabs)
└ 80_staff_exit.py       Staff Exit & Succession (NEW, 240+ LOC, 4 tabs)
```

## HR engines — all 8 wired

| Engine | Std | Page | Status |
|---|---|---|---|
| `peer_learning` | #14 | 42_lms.py | ✅ |
| `coaching_intelligence` | #15 | 2_people.py | ✅ |
| `predictive_performance` | #16 | 2_people.py | ✅ |
| `gamification` | #17 | 2_people.py | ✅ |
| `efficiency` | #18 | 43_pip.py | ✅ |
| `wellness` | #19 | 2_people.py | ✅ |
| `staff_onboarding_engine` | v10.434 | **79_staff_onboarding.py** | **✅ NEW** |
| `staff_exit_engine` | v10.435 | **80_staff_exit.py** | **✅ NEW** |

**100% engine wiring achieved.**

## Verified outcome

| Metric | v10.440 | v10.441 |
|---|---|---|
| Audit gates | 326 | **327** |
| v10.4xx tests | 288 | **309** (+21) |
| Verifier | 820 | **826** (+6) |
| Lockstep batches | 84 | **85** consecutive |
| G162 baseline | 4022 (133) | 4022 (**134** zero-drift) |
| **HR engine wiring** | 75% (6/8) | **100%** (8/8) ✓ |
| **HR module placement** | 100% | **100%** ✓ |
| **HR should-be-but-arent** | 2 | **0** ✓ |
| **HR overall health** | 69.2% | **76.2%** ↑ |
| HR pages | 5 | **7** |
| Standards wiring | 78.8% | **78.8%** ✓ |
| 360 harmony | 100% | **100%** ✓ |
| BSC rescue | 100% | **100%** ✓ |

## Remaining HR rescue priorities (2)

1. **Build out 3 stub pages**: workforce planning (86 LOC), disciplinary (110 LOC), and LMS (199 LOC — close to threshold but still flagged). These have engine wiring already; need content depth.

2. **Add API endpoints for 6 engines**: peer_learning, coaching_intelligence, predictive_performance, gamification, efficiency, wellness. The 2 new pages have endpoints via v10.434/v10.435 work.

v10.442 will address the API endpoints. v10.443 will tackle the stubs + PostgreSQL.

## 10 honest acknowledgements

1. **All 8 HR engines wired = 100% engine wiring dimension.** From 25% at v10.436 audit to 100% in 4 batches (v10.437 placement + v10.438 #14+#17 + v10.440 #18+#19 + v10.441 onboarding+exit pages).

2. **HR Health jumped +7 points** from one batch. New pages count as both "wired engines" and "substantial pages" — double impact.

3. **The 2 new pages are not stubs.** 230+ and 240+ LOC each, 4 tabs each. Real functionality, not placeholders.

4. **Module placement is now perfectly clean.** 7 pages in HR, all belong, no should-be-elsewhere, no should-be-here-but-aren't. The relocation work (v10.437) is locked in.

5. **The dynamic detection patch is the proper fix.** Hard-coded "no page yet" placeholders served a purpose at v10.436 (signaling intent); now they'd be wrong. Detection is dynamic.

6. **Forward-compat preserved.** v10.436 tests check `MISPLACED_HR_PAGES` constant (still present); v10.437 placement check still passes; v10.441 just adds new assertions.

7. **The onboarding page surfaces the "Senior RM Corporate" gap.** Simulator catches the role-with-no-role_kpis case visibly — admin sees the warning before adding a real hire.

8. **The exit page demonstrates 3 strategies side-by-side.** That's the diagnostic value v10.435 promised but couldn't deliver without a UI: comparing strategies at a glance.

9. **No engine code changed.** v10.434 and v10.435 engines already had the right APIs. v10.441 is pure UI work.

10. **The rescue arc is past the halfway mark.** 4 of 6 batches done. v10.442 (APIs) + v10.443 (stubs + PostgreSQL) close it out. HR health targets 90%+ by v10.443.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10441_patch.zip` on top of v10.440 state (overwrite all)
3. `python scripts/verify_local_state.py` → expect **826/826**
4. **Open Streamlit → People → Staff Onboarding** — 4 tabs, try the simulator
5. **Open Streamlit → People → Staff Exit & Succession** — 4 tabs, run a per-staff risk on `300277`
6. **Streamlit → Admin → BSC Health → HR Section Health Audit** — engine wiring **100%**, HR Health **76.2%**, 0 missing pages
7. Tell me **"continue"** → v10.442 = FastAPI endpoints for 6 HR engines

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.424–v10.440~~ | BSC + 360 + HR (diagnose + relocate + wire 4 closed stds + system diag) | **DONE** |
| ~~**v10.441**~~ | **HR Rescue: Build onboarding + exit pages** | **DONE (76.2%)** |
| **v10.442** | HR Rescue: FastAPI endpoints for 6 HR engines | **Next** |
| v10.443 | HR Rescue: PostgreSQL scaffold + stub buildout | |
| v10.444+ | Systemwide rescue per G325 priorities | After HR complete |
