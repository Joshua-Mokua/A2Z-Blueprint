# Changelog — v10.484 Phase O6-B LLM Agent Infrastructure

**Date:** 2026-05-16
**Doctrine source:** *Master Prompt — Enterprise Banking Digital Twin Phase O6-B*
**Joshua mandate:** *"LLM agent infrastructure (tool-calling agents over the simulator)."*
**Audit:** G370 added (**401 honest gates**)
**Tests:** 34/34 v10.484 + 95/95 v10.481-v10.483 regression = **129/129 Phase O4-B onward**
**Combined regression:** 1474+ v10.4xx tests
**Verifier:** 1094 → **1100** (+6 v10.484 checks)
**G162 baseline:** 4022 (**178 consecutive** zero-drift batches)
**Master prompt:** v5.27 → v5.28 (lockstep — **129 consecutive batches**)

---

## 🎯 PHASE O6 COMPLETE — AGENTS CAN DRIVE THE TWIN

```
                          AGENT
                            │
                            ▼
                       AgentPolicy
                  (Deterministic / Random
                   / Scripted / LLM*)
                            │
                            ▼
                      Choose tool
                            │
                            ▼
                     ToolRegistry
                  ┌──────────┴──────────┐
                  ▼                     ▼
              channels              chaos
              scenarios             macro
              ML models             events
              time controls
                  │
                  ▼
              AgentTrajectory + agent.step events
                  │
                  ▼
              AgentBudget enforced
                  │
                  ▼
              agent.run_complete

  * LLM policies plug in via AgentPolicy.choose() — same loop
```

The simulator is no longer just observable — it's drivable by autonomous agents. A tool-calling agent can survey macro state, inspect chaos, train ML models, submit channel transactions, advance sim time, all under deterministic budgets with full trajectory replay.

---

## What was built

### `utils/agents/` (NEW sub-package, 5 modules)

```
utils/agents/
├── __init__.py             ← public exports
├── base.py                 ← types: Tool, Result, Observation, Step, Trajectory, Budget
├── tools.py                ← ToolRegistry + 15 default tools (6 categories)
├── policies.py             ← AgentPolicy + Deterministic + Random + Scripted
└── runner.py               ← AgentRunner deterministic loop + event emission
```

### `base.py` — types

Six frozen-dataclass building blocks define the agent's mental model:

| Type | Purpose |
|---|---|
| `AgentTool` | Typed callable: name + description + handler + schema + category + requires |
| `AgentToolResult` | What a tool returns: success / output / error / latency_ms |
| `AgentObservation` | What the agent sees: step_index + last_result + sim_time + context (cbr/usd_kes/npl/active_chaos_count) + history_summary |
| `AgentStep` | One (tool, args, result, rationale, timestamp) decision |
| `AgentTrajectory` | Full sequence of steps + tool_call_summary helpers |
| `AgentBudget` | Execution limits: max_steps + max_seconds, with `exhausted()` returning the termination reason |

### `tools.py` — ToolRegistry with 15 default tools

Thread-safe singleton (RLock) wrapping every digital-twin capability as a typed callable. `call(name, **kwargs)` wraps both successful results and exceptions in `AgentToolResult` so policies never see raw failures.

| Category | Tools |
|---|---|
| **channel** (2) | `channel:list`, `channel:submit` |
| **scenario** (2) | `scenario:list`, `scenario:run` |
| **chaos** (3) | `chaos:list`, `chaos:activate`, `chaos:active` |
| **macro** (2) | `macro:snapshot`, `macro:apply_shock` |
| **ml** (3) | `ml:list`, `ml:predict`, `ml:train_classifier` |
| **info** (3) | `events:query`, `time:advance`, `time:now` |

Adding a new tool is one `reg.register(AgentTool(...))` call — agents see it immediately.

### `policies.py` — three reference policies

All policies inherit from `AgentPolicy` and implement `choose(observation, available_tools, goal) → (tool_name, args, rationale)`. Returning `(None, {}, reason)` signals clean termination.

**DeterministicPolicy** — state-machine plans for 5 goal keywords:
| Goal substring | Plan |
|---|---|
| `inspect_channels` | list channels → query mpesa events → submit probe transaction |
| `survey_macro` | snapshot macro → query macro.update events |
| `survey_chaos` | list chaos templates → check active chaos |
| `run_scenario` | list scenarios → run the first one |
| `train_model` | submit 2 transactions → train classifier on success label |
| (default) | list channels → snapshot macro |

**RandomPolicy** — seed-deterministic random choice from safe (read-only) tools. By default excludes destructive operations (`channel:submit`, `chaos:activate`, `macro:apply_shock`, `ml:train_classifier`, `time:advance`) so random exploration can't accidentally trash the twin.

**ScriptedPolicy** — replay a fixed `[(tool_name, args), ...]` sequence. Perfect for golden tests and reproducibility checks.

LLM-backed policies can be added later by subclassing `AgentPolicy` — the loop, tool wiring, budget enforcement, and event emission stay identical regardless of where the tool choice originates.

### `runner.py` — AgentRunner deterministic loop

```python
runner = AgentRunner()
result = runner.run(
    policy=DeterministicPolicy(),
    goal="inspect_channels",
    agent_name="probe_bot",
    budget=AgentBudget(max_steps=5, max_seconds=10),
)
```

Each iteration:
1. Check budget. If exhausted → terminate with reason.
2. Build observation from sim clock + macro + chaos + history.
3. Ask policy: which tool, what args, why?
4. If `tool_name is None` → terminate (policy-decided clean exit).
5. Invoke tool via registry. Record step. Emit `agent.step` event.
6. Loop.

On completion: emit `agent.run_complete` event with trajectory summary.

---

## End-to-end smoke (verified)

```
ToolRegistry: 15 tools across 6 categories

DeterministicPolicy: inspect_channels
  Steps: 3  successful: 3  reason: inspection plan complete
  step 0: channel:list   ok=True  keys=['channels']
  step 1: events:query   ok=True  keys=['count', 'events']
  step 2: channel:submit ok=True  keys=['channel', 'status', 'success', 'latency_ms']

DeterministicPolicy: survey_macro
  Steps: 2  reason: macro survey complete

ScriptedPolicy
  Steps: 3  successful: 3  tool_summary={'channel:list':1, 'macro:snapshot':1, 'chaos:list':1}

RandomPolicy (seed=42, max_steps=5)
  Steps: 5  successful: 5  picks: chaos:active, channel:list, macro:snapshot, events:query×2

Event bus: 13 agent.step + 4 agent.run_complete emitted
```

---

## G370 — locks Phase O6-B

G370 verifies on every audit run:
1. Sub-package + 5 modules present
2. ToolRegistry has 15 tools across 6 categories
3. AgentTool rejects non-callable handler at construction
4. ToolRegistry.call wraps successful tool in AgentToolResult
5. ToolRegistry.call wraps exception as success=False
6. DeterministicPolicy walks `inspect_channels` plan to 3 steps
7. AgentRunner respects `max_steps` budget
8. AgentRunner emits `agent.step` events
9. AgentRunner emits `agent.run_complete` event
10. ScriptedPolicy executes exactly script length
11. RandomPolicy is seed-deterministic
12. Prior O6-A (G369) preserved

**G370 currently PASSES.**

---

## Verified outcome

| Metric | v10.483 | v10.484 |
|---|---|---|
| Audit gates | 400 | **401** (G370) |
| Verifier | 1094 | **1100** (+6) |
| Lockstep batches | 128 | **129** |
| G162 baseline | 4022 (177) | 4022 (**178** zero-drift) |
| **Phase posture** | O3-O6-A LOCKED | **O3-O6 COMPLETE** ✅ |
| Channel simulators | 7 | 7 (preserved) |
| Scenarios | 100 | 100 (preserved) |
| Chaos templates | 25 | 25 (preserved) |
| ML modules | 6 | 6 (preserved) |
| **Agent modules** | none | ✅ 5 (base/tools/policies/runner/__init__) |
| **Agent tools** | none | ✅ 15 default tools |
| **Agent policies** | none | ✅ 3 reference (Deterministic/Random/Scripted) |
| Phase O4-B+ tests | 95 | **129 total** (34 new) |
| All prior cert (G354-G369) | preserved | preserved ✓ |

---

## On your end

1. Extract `a2z_v10484_patch.zip` on v10.483 (overwrite all)
2. `python scripts/verify_local_state.py` → **1100/1100**
3. `python scripts/audit.py` → **401/401**
4. **Run a deterministic probe agent**:
   ```python
   from datetime import datetime
   from utils.simulation_clock import (
       get_simulation_clock, reset_simulation_clock, NAIROBI_TZ)
   from utils.agents import (
       AgentRunner, DeterministicPolicy, AgentBudget)

   reset_simulation_clock()
   clock = get_simulation_clock()
   clock.set(datetime(2026, 5, 31, 9, 0, tzinfo=NAIROBI_TZ))

   result = AgentRunner().run(
       policy=DeterministicPolicy(),
       goal="inspect_channels",
       agent_name="probe_bot",
       budget=AgentBudget(max_steps=5),
   )
   print(f"Steps: {result.step_count()}")
   print(f"Successful: {result.trajectory.successful_steps()}")
   print(f"Tool summary: {result.trajectory.tool_call_summary()}")
   ```
5. **Build a scripted agent and replay it deterministically**:
   ```python
   from utils.agents import AgentRunner, ScriptedPolicy
   script = [
       ("macro:snapshot", {}),
       ("chaos:list", {}),
       ("channel:submit",
           {"channel": "mpesa",
            "payload": {"transaction_type": "CustomerPayBillOnline",
                        "msisdn": "254712345678",
                        "amount": 1500, "paybill": "174379"},
            "amount": 1500, "reference": "agent_test"}),
       ("events:query", {"event_type": "integration.mpesa.success",
                          "limit": 3}),
   ]
   result = AgentRunner().run(
       policy=ScriptedPolicy(script),
       goal="test", agent_name="script_bot",
   )
   for step in result.trajectory.steps:
       print(f"  {step.tool_name:25} ok={step.result.success}")
   ```
6. **Pull agent telemetry from the event bus**:
   ```python
   from utils.event_bus import get_event_bus
   bus = get_event_bus()
   for ev in bus.query(event_type="agent.step", limit=10):
       p = ev.payload
       print(f"{ev.timestamp[:19]}  {ev.actor:15} step {p['step_index']}: "
             f"{p['tool_name']:25} ok={p['success']}")
   ```
7. **Register your own custom tool**:
   ```python
   from utils.agents import (
       AgentTool, get_default_tool_registry)
   reg = get_default_tool_registry()
   reg.register(AgentTool(
       name="custom:greet",
       description="Return a greeting",
       handler=lambda *, name="world": {"greeting": f"hello {name}"},
       category="info",
   ))
   # Agents can now use custom:greet
   ```

---

## What this unlocks

- **v10.485-486 O7** training arena can run named drills where agents must survive specific chaos/macro shock combinations
- **v10.487** Olympic-grade cert can verify agent trajectories are reproducible (seed → identical sequence)
- LLM-backed policies (Claude, local models) can plug in via subclass — same registry, same runner, same trajectory schema
- Each Streamlit page can spawn agents for "auto-fill," "what-if-explore," and "stress test" buttons

Roadmap:
- ✅ v10.473-476 O1+O8+O2 · ✅ v10.477-479 O3 · ✅ v10.480-481 O4 · ✅ v10.482 O5 · ✅ v10.483 O6-A · ✅ v10.484 O6-B
- ⏭️ **v10.485** O7-A — Training arena (named drills for chaos survival)
- v10.486 O7-B — Drill scoring + replay
- v10.487 Olympic-grade cert
- v10.488+ Track C — React facelift

---

## 🏥 Patient status

The patient now has organs (channels, macro, chaos), a brain (ML lab), and hands (agents). It can be observed, stressed, learned from, and *autonomously operated* — all deterministically, all replayable, all logged. The body is ready to be put through Olympic-grade trials.

Tell me **"continue"** for v10.485 — Phase O7-A (training arena).
