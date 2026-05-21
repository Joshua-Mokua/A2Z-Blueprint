# Changelog — v10.482 Phase O5 Chaos Engineering

**Date:** 2026-05-15
**Doctrine source:** *Master Prompt — Enterprise Banking Digital Twin Phase O5*
**Joshua mandate:** *"Inject failures across 7 channels during scenarios at specific sim moments."*
**Audit:** G368 added (**398 honest gates**)
**Tests:** 30/30 v10.482 + 152/152 v10.477-v10.481 regression = **182/182 Phase O3-O5**
**Combined regression:** 1408+ v10.4xx tests
**Verifier:** 1075 → **1082** (+7 v10.482 checks)
**G162 baseline:** 4022 (**176 consecutive** zero-drift batches)
**Master prompt:** v5.25 → v5.26 (lockstep — **127 consecutive batches**)

---

## 🎯 CHAOS IS NOW SCHEDULABLE

```
              SIMULATION CLOCK
                    │
              ┌─────┴──────────┐
              ▼                ▼
        TICK SCHEDULER    channels
              │              │
       ┌──────┴──────┐       │
       ▼      ▼      ▼       │
   macro    chaos  custom    │
   bridge   sched           ▼
       │      │         CHAOS INJECTOR
       │      │         (singleton)
       ▼      ▼              │
   macro      ▼              ▼
   state    activate     queried by
            chaos        every submit()
            events
```

The body can now experience controlled, reproducible adversity. A Safaricom outage at 2:30pm. A SWIFT correspondent disconnection during the EOM rush. KES devaluing 5% during a board meeting. Every event fires deterministically at sim moments, composes naturally with normal traffic, recovers cleanly when the window expires.

---

## What was built

### `utils/chaos/` (NEW sub-package, 5 files)

```
utils/chaos/
├── __init__.py             ← public exports
├── base.py                 ← ChaosEvent + ChaosKind + ChaosSeverity
├── injector.py             ← ChaosInjector singleton with channel hooks
├── library.py              ← 25 prebuilt Kenya-realistic templates
└── scheduler.py            ← ChaosScheduler bridges to TickScheduler
```

### `base.py` — types

`ChaosEvent` is a **frozen dataclass** with `name`, `kind`, `when` (tz-aware), `duration`, `severity`, `target` ("*", "mpesa", "rtgs,kic"), `payload`, `realistic_basis`, `tags`.

`ChaosKind` enum (5 values):

| Kind | Effect |
|---|---|
| `CHANNEL_OUTAGE` | 100% failure on the target channel during the window |
| `ELEVATED_FAILURE` | Bumps failure rate (composes multiplicatively) |
| `LATENCY_SPIKE` | Multiplies latency by `payload["multiplier"]` |
| `MACRO_SHOCK` | Delegates to MacroEvolution.apply_shock |
| `SCHEME_DEGRADED` | Card scheme partial outage (failure_rate + scheme tag) |

`ChaosSeverity` enum: INFO / LOW / MEDIUM / HIGH / CRITICAL.

### `injector.py` — ChaosInjector singleton

Thread-safe singleton (RLock) holding currently-active chaos events. Channel `submit()` queries these hooks before normal failure sampling:

| Hook | Purpose |
|---|---|
| `is_channel_outage(channel)` | True if any active CHANNEL_OUTAGE targets the channel |
| `elevated_failure_rate(channel)` | Combined failure rate via $1 - \prod_i (1 - r_i)$ |
| `latency_multiplier(channel)` | Product of all active LATENCY_SPIKE multipliers |
| `active_for_channel(channel)` | Full list of events affecting the channel |

`_prune_expired(now)` is called automatically on each query — events whose `ends_at()` is past `now` are dropped and their `chaos.deactivated` events emitted.

Target matching: `"*"` matches every channel; `"mpesa,ussd"` matches both M-Pesa and USSD via comma split.

Emits `chaos.activated` and `chaos.deactivated` events to the event bus for telemetry.

### `library.py` — 25 prebuilt Kenya-realistic templates

| Category | Count | Examples |
|---|---|---|
| **Channel outages** | 8 | safaricom_mpesa_outage_30min, swift_correspondent_down_4hr, kepss_host_down_60min (takes RTGS+KIC together), atm_network_partition_45min, full_digital_blackout_15min |
| **Elevated failures** | 7 | cards_acquirer_degraded_60min (35%), atm_dispenser_jams_eom (15%), ussd_session_drop_storm_30min (40%), mpesa_callback_blackhole (25%) |
| **Latency spikes** | 4 | swift_latency_spike_3x, cards_3ds_acs_slow (5x), rtgs_kepss_latency_2x, all_channels_latency_spike (2.5x) |
| **Macro shocks** | 4 | kes_devaluation_5pct, cbk_emergency_hike_200bps, credit_shock_npl_plus_300bps, inflation_spike_food (+250bps) |
| **Scheme degraded** | 2 | visa_routing_degraded_60min, mastercard_3ds_outage_30min |

Every template has a `realistic_basis` field citing the real Kenya banking incident or pattern it models. Built via `get_chaos_event(name, when, **overrides)` so callers pick the time.

### `scheduler.py` — ChaosScheduler

Bridges chaos events into the v10.480 TickScheduler:

```python
chaos_sched = ChaosScheduler(scheduler=tick_scheduler)
chaos_sched.schedule(get_chaos_event(
    "safaricom_mpesa_outage_30min",
    when=datetime(2026, 5, 31, 14, 30, tzinfo=NAIROBI_TZ),
))
tick_scheduler.tick(advance_by=timedelta(hours=4))
# At sim 14:30 the outage activates; by 15:00 it has expired
```

`_fire_macro_shock` is special — it delegates to `MacroEvolution.apply_shock` and writes the new state to the global macro singleton, completing the loop between O5 chaos and O4-B macro evolution.

### `channels/base.py` (MODIFIED) — chaos hook

After validation, before normal failure sampling, every channel's `submit()` now consults the injector:

1. **Outage check** — if `is_channel_outage(channel)` returns True, the request fails immediately with `FAILED_HOST_UNAVAILABLE` and `error_code="CHAOS_OUTAGE"`.
2. **Latency scaling** — `_sample_latency() * latency_multiplier(channel)`.
3. **Elevated-failure roll** — if a random roll falls below `elevated_failure_rate(channel)`, request fails with `error_code="CHAOS_FAILURE"`.
4. **Otherwise** — proceeds to normal failure_modes sampling and success path.

Backward-compatible: when no chaos events are active, `elevated_failure_rate = 0.0` and `latency_multiplier = 1.0`, so behaviour is identical to v10.481.

---

## End-to-end smoke (verified)

```
T=12:00  USD/KES=130.00  active chaos: 0
tick(+2h)
T=14:00  active chaos: 0
tick(+45min)
T=14:45  active chaos: ['safaricom_mpesa_outage_30min']
         USD/KES=130.00 (FX shock not yet)
tick(+45min)
T=15:30  active chaos: []   ← outage expired
         USD/KES=136.50 (FX shock fired at 15:00 → +5%)
```

Scheduled chaos events fire at their sim moment, the M-Pesa outage automatically expires after 30 minutes, the FX shock applies at 15:00 and persists. All deterministic and replayable.

---

## G368 — locks Phase O5

G368 verifies on every audit run:
1. Sub-package + 5 modules
2. ChaosKind has 5 values; ChaosSeverity has 5 values
3. CHAOS_LIBRARY has exactly 25 templates
4. `get_chaos_event(name, when)` builds valid events
5. ChaosInjector activates/deactivates, prunes expired
6. `is_channel_outage` returns True during active outage
7. `elevated_failure_rate` composes multiplicatively
8. `submit()` returns CHAOS_OUTAGE during channel outage
9. After window expires, submit() resumes normal behaviour
10. ChaosScheduler wires events to TickScheduler
11. Macro shock chaos applies to global macro state
12. Prior O4 (G366, G367) preserved

**G368 currently PASSES.**

---

## Verified outcome

| Metric | v10.481 | v10.482 |
|---|---|---|
| Audit gates | 397 | **398** (G368) |
| Verifier | 1075 | **1082** (+7) |
| Lockstep batches | 126 | **127** |
| G162 baseline | 4022 (175) | 4022 (**176** zero-drift) |
| **Phase posture** | O3+O4 complete | **O3+O4+O5 LOCKED** ✅ |
| Channel simulators | 7 | 7 (preserved) |
| Scenarios | 100 | 100 (preserved) |
| **Chaos templates** | none | ✅ 25 Kenya-realistic |
| **Chaos kinds** | none | ✅ 5 (outage / elevated / latency / macro / scheme) |
| Phase O3-O5 tests | 152 | **182 total** (30 new) |
| All prior cert (G354-G367) | preserved | preserved ✓ |

---

## On your end

1. Extract `a2z_v10482_patch.zip` on v10.481 (overwrite all)
2. `python scripts/verify_local_state.py` → **1082/1082**
3. `python scripts/audit.py` → **398/398**
4. **Inject a M-Pesa outage and watch traffic fail**:
   ```python
   from datetime import datetime, timedelta
   from utils.simulation_clock import (
       get_simulation_clock, reset_simulation_clock, NAIROBI_TZ)
   from utils.chaos import (
       reset_chaos_injector, get_chaos_injector, get_chaos_event)
   from utils.channels import submit_channel

   reset_simulation_clock(); reset_chaos_injector()
   clock = get_simulation_clock()
   clock.set(datetime(2026, 5, 15, 14, 30, tzinfo=NAIROBI_TZ))

   # Activate outage
   get_chaos_injector().activate(get_chaos_event(
       "safaricom_mpesa_outage_30min", when=clock.now()))

   # All M-Pesa traffic now fails
   r = submit_channel("mpesa",
       payload={"transaction_type": "CustomerPayBillOnline",
                "msisdn": "254712345678", "amount": 1500,
                "paybill": "174379"},
       amount=1500, reference="OUT-1", actor="t")
   print(f"{r.status.value}  error_code={r.error_code}")
   # → failed_host_unavailable  error_code=CHAOS_OUTAGE

   # Advance past 30min window — M-Pesa recovers
   clock.advance(timedelta(hours=1))
   r = submit_channel("mpesa",
       payload={"transaction_type": "CustomerPayBillOnline",
                "msisdn": "254712345678", "amount": 1500,
                "paybill": "174379"},
       amount=1500, reference="OK-1", actor="t")
   print(f"{r.status.value}")   # → success
   ```
5. **Schedule chaos through the tick scheduler**:
   ```python
   from utils.tick_scheduler import TickScheduler
   from utils.chaos import ChaosScheduler

   reset_simulation_clock(); reset_chaos_injector()
   clock.set(datetime(2026, 5, 31, 9, 0, tzinfo=NAIROBI_TZ))
   sched = TickScheduler(clock)
   chaos_sched = ChaosScheduler(scheduler=sched)

   # Schedule a SWIFT outage at 14:00 + KES devaluation at 15:00
   chaos_sched.schedule(get_chaos_event(
       "swift_correspondent_down_4hr",
       when=datetime(2026, 5, 31, 14, 0, tzinfo=NAIROBI_TZ)))
   chaos_sched.schedule(get_chaos_event(
       "kes_devaluation_5pct",
       when=datetime(2026, 5, 31, 15, 0, tzinfo=NAIROBI_TZ)))

   # Fast-forward 8 hours — both events fire at their sim moments
   sched.tick(advance_by=timedelta(hours=8))
   ```
6. **Stream chaos telemetry**:
   ```python
   from utils.event_bus import get_event_bus
   for ev in get_event_bus().query(event_type="chaos.activated", limit=10):
       p = ev.payload
       print(f"{ev.timestamp[:19]}  {p['name']:35} kind={p['kind']} "
             f"target={p['target']:10} sev={p['severity']}")
   ```

---

## What this unlocks

- **v10.483-484 O6** AI/ML evolution can train models on the rich event stream generated by chaos + scenarios + macro
- **v10.485-486 O7** training arena can run named chaos drills ("survive a Safaricom outage during EOM payroll")
- **v10.487** Olympic-grade cert verifies the system against scheduled chaos batteries with deterministic outcomes
- Risk + treasury 360 modules can run "what if" stress tests by activating chaos events and watching propagation

Roadmap:
- ✅ v10.473-476 O1+O8+O2 · ✅ v10.477-479 O3 · ✅ v10.480-481 O4 · ✅ v10.482 O5
- ⏭️ **v10.483** O6-A — AI/ML evolution lab (foundational ML infrastructure)
- v10.484 O6-B — LLM agent infrastructure
- v10.485-486 O7 training arena
- v10.487 Olympic-grade cert
- v10.488+ Track C React facelift

---

## 🏥 Patient status

The patient now has all 6 simulation organs: heart (clock), metabolism (macro), 7 senses (channels), nervous system (telemetry), 100 named situations (scenarios), and now an immune-response capacity — knowing what happens when a Safaricom outage hits, when KES devalues 5%, when KEPSS goes down. The body can be poked at any sim moment and respond realistically. The next phase teaches the body to **learn** from what happens to it.

Tell me **"continue"** for v10.483 — Phase O6-A (AI/ML evolution lab).
