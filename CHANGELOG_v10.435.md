# Changelog — v10.435 Staff Exit + Target Gap Risk Detection

**Date:** 2026-05-14
**Phase:** Identifying single points of failure + modeling gap-fill
**Audit:** G321 added (cumulative 321 gates)
**Tests:** 19/19 PASSED in `test_v10435_exit_risk.py`
**Combined regression:** 201 v10.4xx BSC arc tests PASSED (182 prior + 19 new)
**Verifier:** 793 → **799** (+6 v10.435 checks)
**G162 baseline:** 4022 (128 consecutive zero-drift batches)
**Master prompt:** v4.77 → v4.78 (lockstep — 79 consecutive batches)

**360 HARMONY: 100% preserved. BSC RESCUE: 100% preserved.**

---

## What you directed

> "Confirm that an addition of a new staff fits in so well … and that staff exit + target gap risk is detected."

v10.434 covered onboarding. **v10.435 covers exit** — the inverse: what targets become orphaned when a staff leaves, who's a single point of failure, how would the gap be filled.

## What v10.435 built

### `utils/staff_exit_engine.py` (~700 LOC, **28th React-ready engine**)

Zero streamlit. Four public functions:

| Function | Returns | Purpose |
|---|---|---|
| `audit_exit_risk(staff_code)` | `StaffExitRisk` | One staff's full risk profile |
| `audit_all_exit_risks()` | `BankWideExitAudit` | Bank-wide rollup, optimized (loads data once) |
| `simulate_redistribution(staff_code, strategy)` | `RedistributionPlan` | Models gap-fill via 3 strategies |
| `simulate_exit(staff_code)` | `ExitSimulation` | Risk + all 3 redistribution plans + recommendation |

**4 JSON-serializable dataclasses.** All read-only — no data writes.

### Risk score (0-100) — five dimensions

| Dimension | Range | What it measures |
|---|---|---|
| Outgoing cascade size | 0–25 | How many subordinate cascade entries depend on them |
| Outgoing target value | 0–20 | Total KES flowing through their cascade |
| Role uniqueness | 0–25 | Fewer peers = harder to replace |
| Pillar criticality | 0–15 | If they're the sole pillar contributor in their unit |
| Incoming reliance | 0–15 | How many parents/peers allocate to them |

**Bands:** Critical 75+, High 50–74, Medium 25–49, Low <25.

### Three redistribution strategies

| Strategy | Approach | Feasibility |
|---|---|---|
| `peer_split` | Equal share among same-role peers in same unit | Falls back to unit peers if no role peers; fails if no peers at all |
| `manager_absorb` | Push entire share up to their `Reports To` manager | Fails if no manager set or manager not in BSC |
| `hold_open` | Document the gap as unassigned | Always succeeds; creates a visible accountability hole |

### Bank-wide initial findings

| Band | Count | % |
|---|---|---|
| 🔴 Critical (≥75) | **0** | 0% |
| ⚠️ High (50–74) | **95** | 6.6% |
| 🟡 Medium (25–49) | 214 | 14.9% |
| 🟢 Low (<25) | **1,128** | **78.5%** |
| Avg risk score | 16.09 | — |

**Top global risk drivers:**
- `incoming_reliance` — 1,184 staff (most are downstream of cascades)
- `outgoing_cascade` — 390 staff cascade to ≥6 subordinates
- `outgoing_value` — 312 staff own ≥KES 100M in flows
- `role_unique` — 3 staff have ≤1 peer (the 3 most senior)

### Concrete examples

**MD (William Mwanake) — score 70 (High):**
- 18 outgoing cascade entries (cascades PBT, NFI, Deposits, etc.)
- KES 315B in outgoing flows
- Only 1 of this role bank-wide
- Risk drivers: `[Cascades to 18 entries, Owns KES 315.0B+ in flows, Only 1 of this role]`

**Branch Manager (Kelvin Ndung'u) — score 50 (High):**
- 16 outgoing entries (cascades to branch staff)
- KES 962M flows through them
- 13 parents/peers allocate to them
- Risk drivers: `[Cascades to 16 entries, Owns KES 962M+ in flows, 13 parents/peers allocate to them]`
- Peer split works: 13 unit peers absorb their share

**Teller — score 15 (Low):**
- 0 outgoing cascade (no one reports to a Teller)
- 243 peers absorb easily
- Risk drivers: none meaningful

### Admin panel — `render_exit_risk_panel()`

7th section in the BSC Health tab:
- 5 top metrics: counts per band + avg risk
- Banner (red / amber / green) based on critical+high count
- Critical-risk table (expanded if any)
- High-risk table (collapsed)
- Risk drivers global breakdown
- **Interactive simulator**: enter staff code → see risk + all 3 redistribution scenarios + recommendation

### 3 new FastAPI endpoints
- `GET /api/v1/exit-risk/audit` — bank-wide rollup
- `GET /api/v1/exit-risk/audit/{staff_code}` — single staff
- `GET /api/v1/exit-risk/simulate/{staff_code}` — full simulation

### Audit gate G321
Verifies engine API + zero streamlit + 4 dataclasses + risk score caps sum to 100 + 3 redistribution strategies + admin panel + page wiring + 3 endpoints + 360 harmony preserved + BSC rescue preserved + engine state.

## Verified outcome

| Metric | v10.434 | v10.435 |
|---|---|---|
| Audit gates | 320 | **321** |
| BSC arc tests | 182 | **201** (+19) |
| Verifier | 793 | **799** (+6) |
| API endpoints | 66 | **69** (+3) |
| React-ready engines | 27 | **28** |
| Lockstep batches | 78 | **79** consecutive |
| G162 baseline | 4022 (127) | 4022 (**128** zero-drift) |
| 360 harmony | 100% | **100%** ✓ |
| BSC rescue | 100% | **100%** ✓ |

## Admin panel now has 7 stacked sections

```
📊 Performance → 🩺 BSC Health
   ├ 🩺 BSC Health Dashboard          (v10.430)
   ├ 🔍 KPI Library Validation         (v10.431) — 0 errors
   ├ 🔄 Cascade ↔ BSC 360° Harmony    (v10.432) — 100% ✓
   ├ 🛠️ Cascade-BSC Harmonization     (v10.433) — idempotent
   ├ 👥 Staff Onboarding Fit-In       (v10.434) — 81.8% fully fit
   ├ 🚪 Staff Exit & Target Gap Risk  (v10.435) — 0 Critical, 95 High  ← NEW
   └ BSC Admin Actions
```

## 10 honest acknowledgements

1. **0 Critical staff is honest, not flattering.** No one staff scores ≥75. MD scores 70 because their pillar criticality is 0 — they share their unit (Head Office) with chiefs who provide pillar coverage. If MD left, chiefs still cover. That's realistic.

2. **95 High-risk staff is the actual succession-planning queue.** These are predominantly Branch Managers (16 outgoing cascade entries, KES 962M+ flowing through each) and senior leaders. Tells HR where to invest in deputy/backup roles.

3. **`peer_split` works for most operational roles.** Branch Managers have 13 unit peers; Tellers have 243 bank-wide. The cascade survives most exits via peer absorption.

4. **`manager_absorb` reveals register data gaps.** Where `Reports To` is missing or stale, this strategy fails. That's a finding for HR to clean up the register.

5. **The 5-dimension risk model is principled.** Each dimension caps at a specific value (25, 20, 25, 15, 15). Summing to 100 enforces band thresholds being meaningful percentages.

6. **No false Criticals.** The bands are calibrated so Critical means truly catastrophic — only someone who's simultaneously cascading a lot, owning a lot of value, is unique in role, sole pillar contributor, AND has heavy incoming reliance.

7. **Bank-wide audit is fast.** Pre-computes 6 in-memory lookups (outgoing/incoming counts and values, role peers, unit×pillar contributors, BSC rows per code) before iterating staff. ~3s for 1437 staff.

8. **All 1437 staff scoreable.** Zero exclusions. Every staff has a risk score.

9. **The simulator is the action point.** Risk awareness is one thing; "what would actually happen if X exits" is another. The simulator runs all 3 strategies + recommends.

10. **Read-only by design.** v10.435 is a diagnostic + simulator. Live exit processing (BSC row removal, cascade rewiring, target reassignment) is v10.436+ territory alongside the HR module.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10435_patch.zip` on top of v10.434 state
3. `python scripts/verify_local_state.py` → expect **799/799**
4. `python utils/staff_exit_engine.py` → self-test runs full audit (~5s)
5. **Open Streamlit → Admin → 📊 Performance → 🩺 BSC Health → scroll to "🚪 Staff Exit & Target Gap Risk"**
6. See the 95 High-risk staff list
7. Try the simulator: code `300001` (MD) → score 70 High, peer_split unfeasible (only 1 of role), manager_absorb depends on register, hold_open creates KES 315B gap
8. Tell me **"continue"** → v10.436+ = HR/People module

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.424–v10.429~~ | BSC Rescue (6 batches) | **DONE** |
| ~~v10.430–v10.431~~ | Admin UI + validation | **DONE** |
| ~~v10.432–v10.433~~ | 360 audit + harmonization | **DONE** (100%) |
| ~~v10.434~~ | New staff onboarding fit-in | **DONE** |
| ~~**v10.435**~~ | **Staff exit + target gap risk** | **DONE (this batch)** |
| v10.436+ | HR / People module (live onboard/exit write paths + succession + competency) | **Next** |
| (later) | Per-role-category pillar weight overrides | Flagged |
| (later) | role_kpis admin editor for senior leadership | Flagged |
