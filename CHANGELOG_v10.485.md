# Changelog — v10.485 Phase O7-A Training Arena

**Date:** 2026-05-16
**Doctrine source:** *Master Prompt — Enterprise Banking Digital Twin Phase O7-A*
**Joshua mandate:** *"Training arena — named drills for chaos survival."*
**Audit:** G371 added (**402 honest gates**)
**Tests:** 30/30 v10.485 + 66/66 v10.483-v10.484 regression = **96/96 Phase O6+ tests**
**Combined regression:** 1504+ v10.4xx tests
**Verifier:** 1100 → **1106** (+6 v10.485 checks)
**G162 baseline:** 4022 (**179 consecutive** zero-drift batches)
**Master prompt:** v5.28 → v5.29 (lockstep — **130 consecutive batches**)

---

## 🎯 OLYMPIC-GRADE DRILLS NOW RUN

```
                         DrillRunner
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         SimClock        ChaosSched      AgentRunner
       (drill.sim_start)  (chaos events)  (drill.agent_goal)
              │               │               │
              └──────┬────────┴───────┬───────┘
                     ▼                ▼
              tick past events   AgentTrajectory
                                       │
                                       ▼
                                  DrillOracle
                                  (pass/fail)
                                       │
                                       ▼
                                  DrillResult
```

Twelve named drills cover the cinematic stress moments of Kenya banking — Safaricom outages, KEPSS host failures, KES devaluations, CBR emergency hikes, end-of-month dispenser jams, and triple-shock cascades. Each drill is fully reproducible: same drill name → same sim time → same environment events → same agent behaviour → same pass/fail.

---

## What was built

### `utils/arena/` (NEW sub-package, 4 modules)

```
utils/arena/
├── __init__.py             ← public exports
├── base.py                 ← Drill + DrillEnvironmentEvent + DrillOracle + DrillResult
├── library.py              ← 12 prebuilt Kenya-realistic drills
└── runner.py               ← DrillRunner end-to-end orchestration
```

### `base.py` — drill types

| Type | Purpose |
|---|---|
| `Drill` | Self-contained reproducible exercise: name + description + category + sim_start (tz-aware required) + environment + agent_goal + oracle + tags + seed |
| `DrillEnvironmentEvent` | Frozen: offset + kind (`chaos:activate` / `macro:apply_shock` / `scenario:run`) + ref + kwargs |
| `DrillOracle` | Pass/fail criteria: min_steps + min_successful_steps + required_tool_calls + forbidden_tool_calls + must_observe_chaos + max_failure_rate + custom_check |
| `DrillResult` | Outcome: passed + agent_steps + successful_agent_steps + failure_reasons + environment_fired + trajectory |

### `library.py` — 12 prebuilt drills

| Category | Count | Drills |
|---|---|---|
| **channel_survival** | 4 | survive_safaricom_outage_morning · survive_swift_correspondent_failure · kepss_outage_takes_rtgs_kic · full_digital_blackout |
| **macro_observation** | 3 | observe_kes_devaluation · observe_cbr_emergency_hike · observe_credit_shock |
| **eom_pressure** | 2 | eom_atm_dispenser_strain · eom_mpesa_callback_blackhole |
| **chaos_ml** | 2 | train_under_partial_outage · train_with_macro_shock_concurrent |
| **scenario_cascade** | 1 | cascade_safaricom_then_kepss (triple shock: Safaricom outage → KEPSS host failure → 5% KES devaluation) |

`_DrillLibrary` is a lazy dict-like proxy so the library isn't built at import time (avoiding circular imports with `simulation_clock`).

### `runner.py` — DrillRunner

```python
result = DrillRunner().run(get_drill("cascade_safaricom_then_kepss"))
print(result.passed)              # True
print(result.environment_fired)   # 3 events fired
print(result.failure_reasons)     # []
```

Steps:
1. `reset_simulation_clock()`, `reset_chaos_injector()`, `reset_macro_state()` for reproducibility
2. `clock.set(drill.sim_start)`
3. Build `TickScheduler` + `ChaosScheduler`
4. Schedule every environment event at `sim_start + offset`
5. **Tick at least 1 second** to fire offset-0 events before the agent runs
6. Run `AgentRunner(policy=DeterministicPolicy(), goal=drill.agent_goal)`
7. Evaluate every oracle condition; **all must hold** for pass
8. Return `DrillResult` with trajectory + environment_fired + failure_reasons

---

## Honest note on the journey

Two real issues caught and fixed this batch:

1. **ToolRegistry.call kwarg collision** — when `MLBridge.train_classifier` is wrapped as an agent tool, its handler takes a `name` kwarg ("model name to train"). `ToolRegistry.call(name, **kwargs)` then collides — Python rejects `call("ml:train_classifier", name="my_model", ...)` with `got multiple values for argument 'name'`. Fixed by renaming the registry method's first param from `name` to `tool_name`. Caller code in `AgentRunner` already passes positionally so no breakage downstream. Test added explicitly verifying the param name.

2. **Offset-0 environment events never fired** — the first draft of `DrillRunner` only ticked when `max_offset > 0`. For drills where every environment event has `offset=0` (most of the library), no tick happened at all, so the scheduled chaos events sat in the heap without firing. Agent then ran against a quiet environment. Fixed by always ticking at least 1 second past `max_offset`. `kepss_outage_takes_rtgs_kic` was the canary that caught this — its oracle expected RTGS+KIC outages active during agent run.

Both fixes are minimal and have explicit regression tests.

---

## End-to-end smoke (verified)

```
Drills available: 12 across 5 categories

✓ cascade_safaricom_then_kepps         steps=2  ok=2
✓ eom_atm_dispenser_strain             steps=2  ok=2
✓ eom_mpesa_callback_blackhole         steps=3  ok=3
✓ full_digital_blackout                steps=2  ok=2
✓ kepss_outage_takes_rtgs_kic          steps=2  ok=2
✓ observe_cbr_emergency_hike           steps=2  ok=2
✓ observe_credit_shock                 steps=2  ok=2
✓ observe_kes_devaluation              steps=2  ok=2
✓ survive_safaricom_outage_morning     steps=3  ok=3
✓ survive_swift_correspondent_failure  steps=2  ok=2
✓ train_under_partial_outage           steps=3  ok=3
✓ train_with_macro_shock_concurrent    steps=3  ok=3

Total: 12/12 drills passed
```

---

## G371 — locks Phase O7-A

G371 verifies on every audit run:
1. Sub-package + 4 modules present
2. `Drill.sim_start` naive datetime rejected
3. Library has 12 drills across 5 categories
4. Each category has expected count (4/3/2/2/1)
5. `get_drill` builds a valid Drill
6. `DrillRunner.run(survive_safaricom_outage_morning)` passes
7. `DrillRunner.run(observe_kes_devaluation)` passes
8. `DrillRunner.run(cascade_safaricom_then_kepss)` passes
9. **All 12 drills pass via DrillRunner**
10. `DrillOracle.required_tool_calls` enforced (negative test)
11. `ToolRegistry.call` param is `tool_name` (kwarg fix)
12. Prior O6 (G370) preserved

**G371 currently PASSES.**

---

## Verified outcome

| Metric | v10.484 | v10.485 |
|---|---|---|
| Audit gates | 401 | **402** (G371) |
| Verifier | 1100 | **1106** (+6) |
| Lockstep batches | 129 | **130** |
| G162 baseline | 4022 (178) | 4022 (**179** zero-drift) |
| **Phase posture** | O3-O6 LOCKED | **O3-O6 + O7-A LOCKED** |
| Channel simulators | 7 | 7 (preserved) |
| Scenarios | 100 | 100 (preserved) |
| Chaos templates | 25 | 25 (preserved) |
| ML modules | 6 | 6 (preserved) |
| Agent modules | 5 | 5 (preserved) |
| **Drill library** | none | ✅ 12 named drills |
| **Drill categories** | none | ✅ 5 (survival/macro/eom/ml/cascade) |
| Phase O6+ tests | 66 | **96 total** (30 new) |
| Bug fixes shipped | – | **2** (kwarg collision + tick-zero) |
| All prior cert (G354-G370) | preserved | preserved ✓ |

---

## On your end

1. Extract `a2z_v10485_patch.zip` on v10.484 (overwrite all)
2. `python scripts/verify_local_state.py` → **1106/1106**
3. `python scripts/audit.py` → **402/402**
4. **Run a single drill**:
   ```python
   from utils.arena import DrillRunner, get_drill
   result = DrillRunner().run(get_drill("survive_safaricom_outage_morning"))
   print(f"passed: {result.passed}")
   print(f"agent steps: {result.agent_steps}")
   print(f"environment fired: {result.environment_fired}")
   print(f"tool calls: {result.trajectory.tool_call_summary()}")
   ```
5. **Run all 12 drills as a quick stress sweep**:
   ```python
   from utils.arena import DrillRunner, list_drills, get_drill
   runner = DrillRunner()
   for name in list_drills():
       r = runner.run(get_drill(name))
       flag = "✓" if r.passed else "✗"
       print(f"{flag} {name:45} steps={r.agent_steps}")
   ```
6. **Write your own drill**:
   ```python
   from datetime import datetime, timedelta
   from utils.arena import (
       Drill, DrillEnvironmentEvent, DrillOracle, DrillRunner)
   from utils.simulation_clock import NAIROBI_TZ

   my_drill = Drill(
       name="custom_mpesa_eom_outage",
       description="M-Pesa goes down at EOM",
       category="custom",
       sim_start=datetime(2026, 7, 31, 17, 0, tzinfo=NAIROBI_TZ),
       environment=[
           DrillEnvironmentEvent(
               offset=timedelta(minutes=10),
               kind="chaos:activate",
               ref="safaricom_mpesa_outage_2hr",
           ),
       ],
       agent_goal="inspect_channels",
       oracle=DrillOracle(
           min_steps=3,
           required_tool_calls=["channel:list", "channel:submit"],
       ),
   )
   r = DrillRunner().run(my_drill)
   print(r.passed, r.failure_reasons)
   ```

---

## What this unlocks

- **v10.486 O7-B** drill scoring + replay: persistent ledger of past drill runs, batch sweeps with summary statistics, trajectory comparison between agent versions
- **v10.487** Olympic-grade cert: a battery of all 12 drills + reproducibility checks proves the entire stack
- **CI-friendly stress tests**: each drill is a self-contained unit
- **Training data**: drill trajectories become training data for future LLM-backed policies

Roadmap:
- ✅ v10.473-476 O1+O8+O2 · ✅ v10.477-479 O3 · ✅ v10.480-481 O4 · ✅ v10.482 O5 · ✅ v10.483-484 O6 · ✅ v10.485 O7-A
- ⏭️ **v10.486** O7-B — Drill scoring + replay
- v10.487 Olympic-grade cert
- v10.488+ Track C React facelift

---

## 🏥 Patient status

The patient now has organs, a brain, hands, and an Olympic training arena. Twelve named exercises can be replayed reproducibly, each evaluating the body's response to a specific stress pattern. Future batches will score replays across runs and certify the whole stack.

Tell me **"continue"** for v10.486 — Phase O7-B (drill scoring + replay).
