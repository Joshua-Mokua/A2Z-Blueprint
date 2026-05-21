# Changelog — v10.423 Pillar weights decision (Kaplan-Norton 40/25/25/10)

**Date:** 2026-05-14
**Phase:** Phase 2d (data integrity housekeeping) — **effectively complete**
**Audit:** G309 added (cumulative 309 gates)
**Tests:** 8/8 PASSED in `test_v10423_pillar_weights_decision.py`
**Regression:** 335/335 v10.4xx tests PASSED (327 + 8)
**Verifier:** 724/724 checks pass (717 → 724, +7 v10.423 checks)
**G162 baseline:** 4022 (116 consecutive zero-drift batches)
**Master prompt:** v4.65 → v4.66 (lockstep — 67 consecutive batches)

---

## What this batch is

**Decision applied:** Pillar weights switched from bank-current **68/14/6/12** (Financial-heavy) to **Kaplan-Norton balanced scorecard standard 40/25/25/10**.

This is the only batch in the Phase 2d arc that's a **decision**, not a migration. The infrastructure to vary pillar weights was already built in v10.386. v10.423 just exercises it via the existing canonical path with Joshua's chosen values.

| Pillar | Was | Now |
|---|---|---|
| Financial | 0.68 | **0.40** |
| Customer Focus | 0.14 | **0.25** |
| Operational Excellence | 0.06 | **0.25** |
| People & Learning | 0.12 | **0.10** |

## Admin variability — confirmed

The admin can change pillar weights at any time via:

`pages/7_admin.py` → **KPI Library** → **⚖️ Pillar weights**

The editor was built in v10.386 with:
- Sum-to-1.0 validation
- "No dead organs" check (all 4 pillars required, no zero values allowed)
- Canonical save via `utils.pillar_weights_canonical.save_pillar_weights()`
- Full audit-trail to `data/pillar_weights_history.json` with OLD/NEW + actor + reason

Banks with different cultures or regulatory regimes can therefore set their own splits — for example, a Tier-1 capital-constrained bank might choose 60/15/15/10 (heavier Financial), while a customer-service-led bank might choose 30/40/20/10. The infrastructure supports any valid 4-component split summing to 1.0.

## What v10.423 did

1. Called `utils.pillar_weights_canonical.save_pillar_weights({...}, actor='Joshua', reason='v10.423 Kaplan-Norton balanced scorecard decision...')`
2. The canonical save validated + persisted to `data/kpi_library.json::pillar_weights`
3. The canonical save appended an entry to `data/pillar_weights_history.json` with OLD (68/14/6/12) + NEW (40/25/25/10) + actor + reason
4. Added G309 audit gate verifying all of the above
5. Added 8 integration tests (correctness + history + admin editor presence)

**No new engine. No code migration. No file structure change.** Just a data change recorded through the existing canonical path.

## Verified outcome

| Metric | v10.422 | v10.423 |
|---|---|---|
| Audit gates | 308 | **309** |
| v10.4xx tests | 327 | **335** (+8) |
| Verifier | 717 | **724** (+7) |
| API endpoints | 40 | 40 (no new) |
| Master prompt lockstep | 66 | **67** consecutive |
| G162 baseline | 4022 (115) | 4022 (**116** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10423_patch.zip` on top of v10.422 state
3. `python scripts/verify_local_state.py` → expect **724/724**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. Open `data/kpi_library.json` and confirm `pillar_weights` now shows `0.4 / 0.25 / 0.25 / 0.1`
6. Launch Streamlit → log in as Admin → Admin → KPI Library → ⚖️ Pillar weights → see the new values, can edit + save freely
7. Open `data/pillar_weights_history.json` to see the v10.423 change record with timestamp + reason

The change is now reflected in every BSC computation downstream — final scores will reweight to balance Customer Focus + Operational Excellence higher and Financial lower than before. Existing actuals, targets, and cascade data are unaffected; only the rollup weighting changes.

---

## What's pending (cascade module) + what's now functional

**Cascade module — feature-complete after v10.418:**

| Feature | Status | Batch |
|---|---|---|
| F2 buffer engine + MD per-KPI cap | ✓ Done | v10.414 |
| F2 per-allocation stretch tuner | ✓ Done | v10.415 |
| F3 retain authorization surface | ✓ Done | v10.416 |
| F3 retain validation (compliance display) | ✓ Done | v10.418 |
| F4 regenerator preserves manual | ✓ Done | v10.404 |
| F5 dual-view BSC (My targets cards) | ✓ Done | v10.417 |
| Role weight renormalization | ✓ Done | v10.419 |
| KPI library dedup | ✓ Done | v10.420 |
| Backup retention cleanup | ✓ Done | v10.421 |
| Retired test audit | ✓ Done | v10.422 |
| **Pillar weights (Kaplan-Norton)** | **✓ Done (this batch)** | **v10.423** |

**Cascade roadmap remaining:**

| Concern | Module location | Priority |
|---|---|---|
| BSC scorecard table dual-view (currently only My targets cards show it) | `pages/1_perform.py` | LOW — engine + endpoint ready, just needs render pickup |

That's the **only** cascade item left, and it's a 30-minute render update to the BSC table in the perform page. Cascade is otherwise fully functional.

---

## What's pending (other modules) + decisions to be made

### 🩺 Modules in the body that need attention

Based on the locked backlog in memory, the modules that still need work to "function as one":

**1. CBS / Actuals integration** — `pages/15_cbs.py` + `utils/actuals_engine.py`

| Sub-item | Status | Decision needed? |
|---|---|---|
| CBS baseline computation (snapshot 31 Dec 2025 per RM for YoY) | Pending | **YES — what's the canonical snapshot trigger? Manual? Auto-cron?** |
| Live actuals engine (CBS data refresh auto-updates KPI actuals) | Pending | **YES — when does CBS re-load happen? Streamlit cache key, or explicit Admin button?** |
| PBT computation from CBS data | Pending | **YES — what's the PBT formula spec? (Revenue - Expenses - Provisions - Tax? Or a different breakdown?)** |

**2. BSC scorecard** — `pages/1_perform.py`

| Sub-item | Status | Decision needed? |
|---|---|---|
| MD BSC to show bank targets once set | Pending | No — known fix (just needs to pull from `bank_targets.json` via `casc.get_bank_target()` instead of `get_what_i_was_given`) |
| BSC scorecard table dual-view (v10.417 engine already built) | Pending | No — engine ready, just needs render update |
| BSC compliance column (v10.418 engine ready) | Pending | No — same |

**3. CRM / Pipeline** — `pages/3_pipeline.py`

| Sub-item | Status | Decision needed? |
|---|---|---|
| Pipeline analytics for MD (confirmed fixed earlier) | Done | No |
| Any remaining gaps? | Unknown to me | **YES — please flag if pipeline has known issues** |

**4. Data generation** — `generate_staff.py` + `compute_actuals.py`

| Sub-item | Status | Decision needed? |
|---|---|---|
| Some branch roles missing from certain branches | Pending | **YES — fix the generator, or accept as realistic gap (some branches in real-life don't have a Credit Manager, etc.)?** |

### Open decisions for you

The following need a verdict before the next module rescue can proceed cleanly:

1. **CBS snapshot trigger** — Manual button in Admin? Streamlit on-demand cache refresh? Auto-cron at midnight on 1st of month?
2. **Live actuals refresh timing** — Real-time on every BSC page load (slow), nightly batch (fresh-ish), or admin-triggered (controlled)?
3. **PBT formula spec** — Need the exact accounting breakdown. Bank-specific (Ecobank Kenya FLEXCUBE 12 chart-of-accounts) or canonical IFRS structure?
4. **Generator branch coverage** — Fix to ensure every branch has every role, or accept as realistic gap?
5. **Next module to rescue** — Your call. I see three candidate targets:
   - **BSC scorecard** (`pages/1_perform.py`): 3 known issues, all engines ready, ~2-3 batches of work, no decisions blocked
   - **CBS / live actuals** (`pages/15_cbs.py` + `actuals_engine.py`): bigger lift, needs the 3 decisions above first
   - **Admin module audit** (`pages/7_admin.py`): hasn't been deep-reviewed in this arc; may have stale fields

### My recommendation for the next module rescue

**Start with BSC scorecard (`pages/1_perform.py`).** Reasons:

- Zero blocked decisions — every needed engine + endpoint already exists
- High visible impact — MD/exec users open BSC daily, fixing the 3 issues makes the body's "face" work properly
- Quick wins build momentum — 2-3 small batches, all with the same pattern Phase 2d locked in
- Sets up CBS rescue next — once MD BSC pulls bank targets correctly, the CBS live-actuals wiring has a clear sink to write into

Suggested batch sequence:
- **v10.424** — BSC scorecard dual-view + compliance render (consume v10.417/v10.418 engines)
- **v10.425** — MD BSC pulls bank targets from bank_targets.json (the known issue from memory)
- **v10.426** — BSC scorecard compliance column for managers (extension)

Then pivot to CBS once you've made the 3 decisions on snapshot / refresh / PBT formula.

Tell me which path you want and any decisions, and I'll proceed.
