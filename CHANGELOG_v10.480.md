# Changelog — v10.480 Phase O4-A Simulation Clock + Tick Scheduler

**Date:** 2026-05-15
**Doctrine source:** *Master Prompt — Enterprise Banking Digital Twin Phase O4-A*
**Joshua mandate:** *"Time evolution (simulation clock + tick-based propagation)."*
**Audit:** G366 added (**396 honest gates**)
**Tests:** 29/29 v10.480 + 31/31 v10.479 + 30/30 v10.478 + 29/29 v10.477 = **119/119 channel + scenario + clock tests**
**Combined regression:** 1345+ v10.4xx tests
**Verifier:** 1064 → **1070** (+6 v10.480 checks)
**G162 baseline:** 4022 (**174 consecutive** zero-drift batches)
**Master prompt:** v5.23 → v5.24 (lockstep — **125 consecutive batches**)

---

## 🎯 PHASE O4 BEGUN — TIME IS NOW CONTROLLABLE

```
7 channels → 100 scenarios → telemetry/lineage → anomaly observers
                                    ▲
                                    │
                              SIMULATION CLOCK
                                    │
                              ▼          ▼
                   batch cutoffs   tick scheduler
                   respond to      fires callbacks
                   sim time         at sim moments
```

Before this batch the simulation was time-blind. KIC batch windows checked `datetime.now()`, event bus stamped events with wall time, scenarios couldn't say "run this payroll at 4:31pm just past the cutoff." Now:

- **Set the clock to any moment** — `clock.set(datetime(2026, 5, 15, 11, 25, tzinfo=NAIROBI_TZ))` and the entire body reacts as if it's 11:25am Nairobi
- **Advance it by deltas** — `clock.advance(timedelta(minutes=10))` jumps the world 10 sim minutes
- **Schedule callbacks at sim moments** — `sched.schedule_at(cutoff_time, fire_cutoff_alert)` runs when the clock crosses that point
- **Recurring heartbeats** — `sched.schedule_recurring(start_at=..., interval=timedelta(minutes=15))` for periodic events

And critically: **all of this is backward-compatible**. When the sim clock is inactive (the default), every component falls through to wall-clock time. No changes for callers that don't opt in.

---

## What was built

### `utils/simulation_clock.py` (NEW)

**Setting:** A controllable virtual clock independent of wall-clock time.

```python
class SimulationClock:
    def activate(self) / deactivate(self)
    def set(self, when: datetime) -> None   # tz-aware required
    def advance(self, delta: timedelta) -> datetime
    def reset(self) -> None                  # for test isolation
    def now(self) -> datetime                # sim time or wall UTC
    def now_nairobi(self) -> datetime        # converted to UTC+3
    def is_active(self) -> bool

# Module helpers
get_simulation_clock() -> SimulationClock    # lazy singleton
sim_now() -> datetime                         # drop-in for datetime.now(UTC)
sim_now_nairobi() -> datetime
reset_simulation_clock() -> None
NAIROBI_TZ = timezone(timedelta(hours=3))     # Kenya has no DST
```

| Property | Behaviour |
|---|---|
| **Thread-safe** | All mutations gated by internal RLock |
| **Backward-compat** | `sim_now()` returns wall UTC when inactive |
| **TZ-strict** | `set()` requires timezone-aware datetime — no ambiguity |
| **Anchor + offset model** | `set()` anchors, `advance()` accumulates offset |
| **Single source of truth** | Global singleton via `get_simulation_clock()` |

### `utils/tick_scheduler.py` (NEW)

**Setting:** Deterministic scheduling on top of the sim clock.

```python
class TickScheduler:
    def __init__(self, clock: SimulationClock = None)
    def schedule_at(when, callback, *, priority=0, label="") -> str
    def schedule_recurring(*, start_at, interval, callback, ...) -> str
    def cancel(callback_id: str) -> bool
    def clear() -> int
    def tick(advance_by=None, max_fires=10_000) -> List[Any]
    def pending(self) -> int
    def fired_count(self) -> int
    def peek_next(self) -> Optional[ScheduledCallback]
```

| Feature | Detail |
|---|---|
| **Heap-backed queue** | Pending callbacks live in a min-heap keyed by `(when, -priority, insertion_seq)` |
| **Deterministic ties** | Same `when` + same priority → fires in **insertion order** |
| **Priority override** | Higher priority fires first when `when` ties |
| **Recurring callbacks** | Re-add themselves to the heap after firing |
| **tick(advance_by=delta)** | Advances clock then fires all due in one atomic pass |
| **Cancellation** | `cancel(id)` removes pending callback; `clear()` wipes all |
| **Thread-safe** | Internal RLock; `_INSERTION_SEQ` counter is process-wide |
| **Bounded firing** | `max_fires=10_000` per tick to prevent runaway recurring |

### `utils/channels/kic.py` (MODIFIED) — time-aware batch windows

KIC's `format_message()` now calls `sim_now()` instead of `datetime.now(timezone.utc)` when determining the batch window. When the sim clock is active, the cutoff logic responds to simulation time. When inactive (default), behaviour is identical to v10.479. One-line API change, full backward compatibility.

```python
def format_message(self, req):
    txn_type = req.payload.get("transaction_type", "EFT_CREDIT")
    now = sim_now()                          # ← was datetime.now(timezone.utc)
    nairobi = now.astimezone(NAIROBI_TZ)
    # ... rest unchanged
```

### `utils/scenarios/base.py` (MODIFIED) — `ScenarioContext.clock`

`ScenarioContext` gains a `.clock` property that returns the global sim clock. Scenarios can drive simulation time:

```python
def my_scenario(ctx: ScenarioContext):
    ctx.clock.set(datetime(2026, 5, 31, 11, 25, tzinfo=NAIROBI_TZ))
    # Run payroll just before KIC cutoff — batches enter MORNING window
    for emp in employees:
        ctx.submit_channel("kic", payload={...}, amount=emp.salary)
    ctx.clock.advance(timedelta(minutes=10))  # → 11:35, past cutoff
    # Anything after this enters AFTERNOON window
    for late in late_employees:
        ctx.submit_channel("kic", payload={...}, amount=late.salary)
```

### `utils/event_bus.py` (MODIFIED) — sim-time event timestamps

`emit()` now sources timestamps via `sim_now()` when the sim clock is active. The event timeline stays consistent with simulation time, which means `query(since=scenario_start)` works correctly even when the scenario is running in fast-forwarded sim time.

Lazy import inside the function — no hard dependency on `simulation_clock`. If anything goes wrong importing, falls back to wall UTC.

---

## End-to-end smoke (verified)

```python
# Scenario drives the clock; KIC responds
ctx.clock.set(datetime(2026, 5, 15, 11, 0, tzinfo=NAIROBI_TZ))
# 5 KIC EFTs → all show BatchWindow="MORNING"
ctx.clock.advance(timedelta(hours=1))   # 11:00 → 12:00
# 5 KIC EFTs → all show BatchWindow="AFTERNOON"
```

Before-cutoff windows: `['MORNING', 'MORNING', 'MORNING', 'MORNING', 'MORNING']`
After-cutoff windows:  `['AFTERNOON', 'AFTERNOON', 'AFTERNOON', 'AFTERNOON', 'AFTERNOON']`

The body responds to simulation time exactly as it would to wall time.

---

## G366 — locks Phase O4-A

G366 verifies on every audit run:
1. `utils/simulation_clock.py` exists with `SimulationClock` class + all methods + module helpers + `NAIROBI_TZ`
2. `utils/tick_scheduler.py` exists with `TickScheduler` + `ScheduledCallback` + full API
3. Clock is inactive by default (`is_active() == False` after reset)
4. `set()` activates clock and anchors to specified moment
5. `advance(delta)` moves clock forward by `delta`
6. `sim_now()` returns wall UTC when inactive
7. `sim_now()` returns sim time when active
8. Scheduler fires callbacks in `(when, priority, insertion)` order
9. Recurring callbacks re-schedule themselves correctly
10. KIC channel uses `sim_now()` for batch window selection
11. `ScenarioContext.clock` returns the global sim clock
12. event_bus uses `sim_now()` for timestamps when sim clock active
13. Prior O3 cert (G363, G364, G365) preserved

**G366 currently PASSES.**

---

## Verified outcome

| Metric | v10.479 | v10.480 |
|---|---|---|
| Audit gates | 395 | **396** (G366) |
| Verifier | 1064 | **1070** (+6) |
| Lockstep batches | 124 | **125** |
| G162 baseline | 4022 (173) | 4022 (**174** zero-drift) |
| **Phase posture** | O1+O8+O2+O3 complete | **O3 LOCKED + O4-A LIVE** |
| Channel simulators | 7 | 7 (preserved) |
| Scenarios | 100 | 100 (preserved) |
| **Sim clock** | none | ✅ controllable |
| **Tick scheduler** | none | ✅ deterministic |
| Channel + scenario + clock tests | 90 | **119 total** (29 new) |
| All prior cert (G354-G365) | preserved | preserved ✓ |

---

## On your end

1. Extract `a2z_v10480_patch.zip` on v10.479 (overwrite all)
2. `python scripts/verify_local_state.py` → **1070/1070**
3. `python scripts/audit.py` → **396/396**
4. **Set the world to a specific moment**:
   ```python
   from datetime import datetime, timedelta
   from utils.simulation_clock import (
       get_simulation_clock, sim_now_nairobi, NAIROBI_TZ, reset_simulation_clock
   )
   clock = get_simulation_clock()
   clock.set(datetime(2026, 5, 31, 11, 25, tzinfo=NAIROBI_TZ))
   print(f"sim time now: {sim_now_nairobi()}")  # 11:25am EAT
   clock.advance(timedelta(minutes=20))
   print(f"after 20min:  {sim_now_nairobi()}")  # 11:45am EAT
   reset_simulation_clock()
   ```
5. **Schedule a callback at a sim moment**:
   ```python
   from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
   from utils.tick_scheduler import TickScheduler
   clock = get_simulation_clock()
   clock.set(datetime(2026, 5, 15, 9, 0, tzinfo=NAIROBI_TZ))
   sched = TickScheduler(clock)
   sched.schedule_at(
       datetime(2026, 5, 15, 11, 30, tzinfo=NAIROBI_TZ),
       lambda: print(f"KIC morning cutoff just hit at sim {sched.clock.now_nairobi()}"),
       label="kic_morning_cutoff",
   )
   sched.tick(advance_by=timedelta(hours=3))
   # KIC morning cutoff just hit at sim 2026-05-15 11:30:00+03:00
   ```
6. **Watch KIC respond to sim time**:
   ```python
   from utils.channels import submit_channel
   clock.set(datetime(2026, 5, 15, 10, 0, tzinfo=NAIROBI_TZ))
   r = submit_channel("kic", payload={"transaction_type":"EFT_CREDIT", "beneficiary_bank_code":"011"},
                      amount=50_000, debit_account="x", credit_account="y", reference="A")
   print(r.raw_response.get("BatchWindow"))  # MORNING

   clock.set(datetime(2026, 5, 15, 13, 0, tzinfo=NAIROBI_TZ))
   r = submit_channel("kic", payload={"transaction_type":"EFT_CREDIT", "beneficiary_bank_code":"011"},
                      amount=50_000, debit_account="x", credit_account="y", reference="B")
   print(r.raw_response.get("BatchWindow"))  # AFTERNOON
   ```
7. **Scenario controls time across cutoff**:
   ```python
   from datetime import datetime, timedelta
   from utils.simulation_clock import NAIROBI_TZ
   from utils.scenarios.base import (
       Scenario, ScenarioCategory, ScenarioSeverity, ScenarioRunner
   )

   def cross_cutoff(ctx):
       ctx.clock.set(datetime(2026, 5, 15, 11, 20, tzinfo=NAIROBI_TZ))
       before = ctx.submit_channel("kic",
           payload={"transaction_type":"EFT_CREDIT", "beneficiary_bank_code":"011"},
           amount=50_000, debit_account="x", credit_account="y")
       ctx.clock.advance(timedelta(minutes=20))
       after = ctx.submit_channel("kic",
           payload={"transaction_type":"EFT_CREDIT", "beneficiary_bank_code":"011"},
           amount=50_000, debit_account="x", credit_account="y")
       return {
           "before_window": (before.raw_response or {}).get("BatchWindow"),
           "after_window":  (after.raw_response or {}).get("BatchWindow"),
       }

   s = Scenario(name="cutoff_cross", category=ScenarioCategory.OPERATIONAL,
                description="t", runner=cross_cutoff,
                severity=ScenarioSeverity.INFO,
                realistic_basis="EOM payroll batches often span the 11:30am cutoff")
   r = ScenarioRunner(detect_anomalies=False).run(s, seed=1)
   print(r.scenario_output)
   # {'before_window': 'MORNING', 'after_window': 'AFTERNOON'}
   ```

---

## What this unlocks

- **v10.481 O4-B** can now make economic state (rates, FX, GDP, NPL) drift over **sim time** by hooking into the tick scheduler
- **v10.482 O5** chaos engineering can schedule outages at specific sim moments
- **v10.485-486 O7** training drills can run accelerated time ("see how your branch handles a full week in 30 seconds")
- **v10.487** cert tests can verify time-dependent behaviour reproducibly

Roadmap:
- ✅ v10.473-476 O1+O8+O2 · ✅ v10.477-479 O3 · ✅ v10.480 O4-A
- ⏭️ **v10.481** O4-B — Macro economic state (rates, FX, GDP, NPL drift accruing over sim time)
- v10.482 O5 — Chaos engineering
- v10.483-484 O6 — AI/ML/LLM evolution
- v10.485-486 O7 — Training arena
- v10.487 Olympic-grade cert
- v10.488+ Track C — React facelift

---

## 🏥 Patient status

The patient now has a heartbeat the simulator can control. Time can fast-forward to test EOM behaviour without waiting 30 days. Time can rewind for replay. Cutoffs respect simulation time. Recurring callbacks can simulate the steady rhythms of a working day — branches opening at 8:30am, KIC morning batch closing at 11:30am, RTGS cutoff at 4:30pm — all on a controllable axis.

Tell me **"continue"** for v10.481 — Phase O4-B (macro economic state).
