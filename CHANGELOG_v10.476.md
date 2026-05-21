# Changelog — v10.476 Phase O2-B AI Explainability + Heatmaps + Anomalies + API Telemetry

**Date:** 2026-05-15
**Doctrine source:** *Master Prompt — Enterprise Banking Digital Twin Phase O2*
**Joshua mandate:** *"AI explainability tracking, operational heatmaps, anomaly observability, API telemetry."*
**Audit:** G362 added (cumulative **394 gates**)
**Tests:** 27/27 v10.476 integration tests PASS
**Combined regression:** 1227+ v10.4xx tests
**Verifier:** 1034 → **1041** (+7 v10.476 checks)
**G162 baseline:** 4022 (**170 consecutive** zero-drift batches)
**Master prompt:** v5.19 → v5.20 (lockstep — **121 consecutive batches**)

---

## 🎯 Phase O2 COMPLETE

```
Phase O2 — Truth, Telemetry & Observability
  ✅ v10.475 O2-A — Event bus + transaction lineage + workflow replay
  ✅ v10.476 O2-B — AI explainability + heatmaps + anomalies + API telemetry
```

The nervous system is fully online. Every transaction, every workflow, every AI inference, every API call is now observable, traceable, replayable, **explainable**, and **anomaly-checked**.

---

## Four new modules

### 1. `utils/ai_explainability.py` (NEW) — every AI decision explained

```python
did = record_ai_decision(
    model="credit_alt_scoring",
    prompt={"applicant": "C-001", "income": 95_000},
    response={"decision": "approve", "limit_kes": 800_000},
    reasoning_factors=[
        {"factor": "income",     "value": 95_000, "weight": 0.35},
        {"factor": "kyc_score",  "value": 0.94,   "weight": 0.40},
        {"factor": "existing_dpd","value": 0,      "weight": -0.10},
        {"factor": "tenure_years","value": 4.2,    "weight": 0.15},
    ],
    confidence=0.87, latency_ms=23.4,
    actor="ai_engine", entity_id="APPLICATION_001",
    module="credit",
)

card = decision_explanation_card(did)
# → top_drivers sorted by |weight|:
#   kyc_score   value=0.94   weight=+0.40 (positive)
#   income      value=95000  weight=+0.35 (positive)
#   tenure_years value=4.2   weight=+0.15 (positive)
```

API: `record_ai_decision`, `decision_explanation_card`, `get_ai_decisions`, `model_stats`. Persists to `ai_decisions.jsonl` (mode-aware via Phase O8). Emits `ai.inference` event into event_bus. 5 self-tests pass.

`model_stats(model)` seeds Phase O6 drift detection — returns count, mean confidence, mean latency, and top factor frequency for any model.

### 2. `utils/operational_heatmap.py` (NEW) — the "what's on fire" view

| Function | What it does |
|---|---|
| `bottleneck_analysis()` | Pairs `*.started` with `*.completed/.failed` via `correlation_id`; returns LatencyDistribution (p50/p95/p99/mean/max) keyed by `event_type@module` |
| `queue_depth_by_state()` | Walks `workflow.transition` events to count items currently in each state |
| `approval_latency_per_module()` | Per-module p50/p95/p99 of time from first-seen → `approved` transition |
| `module_activity_heatmap(hours_back=24)` | Events per (module, hour) bucket — for dashboard tiles |
| `heatmap_summary()` | One-shot all-in-one for ops dashboards |

6 self-tests pass.

### 3. `utils/anomaly_observer.py` (NEW) — auto-surface deviations

Four detection rules — intentionally conservative to avoid false-positive fatigue (Phase O6 will broaden these):

| Rule | What it flags | Severity |
|---|---|---|
| **R1 volume spike** | Hour bucket count > rolling_mean + 3σ, ≥5 baseline hours, ≥5 events | warning |
| **R2 failure surge** | `.failed` ratio ≥30% in 1h with ≥5 failed events per family | error |
| **R3 stuck workflow** | Non-terminal state for >48h (TERMINAL_STATES = `{approved, rejected, cancelled, executed, closed}` exempted) | warning |
| **R4 critical burst** | >3 critical-severity events in 1h | critical |

```python
findings = detect_anomalies(emit_events=True)
# Each finding becomes an anomaly.detected event in the event_bus
```

6 self-tests pass.

### 4. `utils/api_telemetry.py` (NEW) — p50/p95/p99 per endpoint

```python
from utils.api_telemetry import track_api_call

@track_api_call("/v1/credit/score", method="POST")
def score_application(request): ...

# Latency + status code automatically recorded.
# Decorator catches exceptions → status_code=500.

summary = get_telemetry_summary(hours_back=24)
# → {"/v1/credit/score": {"count": 20, "p50_ms": 2.14, "p95_ms": 2.17,
#                          "error_rate": 0.0, ...}}
```

API: `record_call`, `track_api_call` decorator, `get_latency_distribution`, `get_telemetry_summary`. JSONL persistence at `api_telemetry.jsonl` (mode-aware). 5 self-tests pass.

---

## End-to-end demo (verified)

```python
# 1. AI decision  →  ai.inference event
did = record_ai_decision(model="credit_alt_scoring", ...)
# event_bus.query(event_type="ai.inference") returns the emission

# 2. Heatmap aggregates from events emitted in v10.475 + v10.476
heatmap_summary()
# Queue depth states:  ['submitted', 'approved', 'under_review']
# Approval-latency modules:  ['credit', 'workflow']
# Bottlenecks tracked:  1 metric (actuals.refresh@bsc_cascade)

# 3. Anomaly observer scans
detect_anomalies(emit_events=True)
# → 0 findings against clean test data
# → emits anomaly.detected events for any real findings

# 4. API telemetry on a real endpoint
@track_api_call("/v1/credit/score")
def score_one(app): time.sleep(0.002); return 0.85
for i in range(20): score_one(f"app_{i}")
# /v1/credit/score  count=20  p50=2.14ms  p95=2.17ms
```

---

## G362 — locks Phase O2-B

G362 verifies on every audit run:
1. `utils/ai_explainability.py` exists with `AIDecision` + `record_ai_decision` + `decision_explanation_card` + `get_ai_decisions` + `model_stats`
2. `utils/operational_heatmap.py` exists with `bottleneck_analysis` + `queue_depth_by_state` + `approval_latency_per_module` + `module_activity_heatmap` + `heatmap_summary` + `LatencyDistribution`
3. `utils/anomaly_observer.py` exists with `Anomaly` + `detect_anomalies` + `anomaly_summary` + all 4 detection rules (`_rule_volume_spike` / `_rule_failure_surge` / `_rule_stuck_workflow` / `_rule_critical_burst`)
4. `utils/api_telemetry.py` exists with `APICallRecord` + `record_call` + `track_api_call` + `get_latency_distribution` + `get_telemetry_summary`
5. Live smoke test: AI decision emits `ai.inference` event, `detect_anomalies()` returns a list
6. Mode awareness: both `_explain_path()` and `_telemetry_path()` resolve via Phase O8 `environment_paths`
7. Prior cert (G354-G361) preserved

**G362 currently PASSES.**

---

## Verified outcome

| Metric | v10.475 | v10.476 |
|---|---|---|
| Audit gates | 393 | **394** (G362) |
| Verifier | 1034 | **1041** (+7) |
| Lockstep batches | 120 | **121** |
| G162 baseline | 4022 (169) | 4022 (**170** zero-drift) |
| **Phase posture** | O1 + O8 + O2-A | **O1 + O8 + O2 (COMPLETE)** ✅ |
| AI decisions explainable | absent | **`record_ai_decision` + top-3 driver cards** |
| Operational heatmaps | absent | **5 views: bottleneck / queue / approval / activity / summary** |
| Anomaly auto-detection | absent | **4 rules emitting `anomaly.detected`** |
| API endpoint telemetry | absent | **`@track_api_call` decorator with p50/p95/p99** |
| Drift baseline (model_stats) | absent | **per-model count/confidence/latency/top-factors** |
| All prior cert (G354-361) | preserved | preserved ✓ |

---

## On your end

1. Extract `a2z_v10476_patch.zip` on v10.475 (overwrite all)
2. `python scripts/verify_local_state.py` → **1041/1041**
3. `python scripts/audit.py` → **394/394**
4. **Self-tests** for each new module:
   ```bash
   python utils/ai_explainability.py      # → ai_explainability self-test passed
   python utils/operational_heatmap.py    # → operational_heatmap self-test passed
   python utils/anomaly_observer.py       # → anomaly_observer self-test passed
   python utils/api_telemetry.py          # → api_telemetry self-test passed
   ```
5. **Record an AI decision and see the explanation card**:
   ```python
   from utils.ai_explainability import (
       record_ai_decision, decision_explanation_card,
   )
   did = record_ai_decision(
       model="my_model", prompt={"q": "approve?"}, response={"a": "yes"},
       reasoning_factors=[
           {"factor": "income", "value": 60_000, "weight": 0.4},
           {"factor": "kyc",    "value": 0.92,   "weight": 0.5},
       ],
       confidence=0.88,
       actor="me", entity_id="APP_001", module="credit",
   )
   print(decision_explanation_card(did))
   ```
6. **Instrument an endpoint**:
   ```python
   from utils.api_telemetry import track_api_call, get_latency_distribution
   @track_api_call("/v1/my_endpoint")
   def my_handler(x): return x * 2
   for i in range(50): my_handler(i)
   print(get_latency_distribution("/v1/my_endpoint"))
   ```
7. **Scan for anomalies**:
   ```python
   from utils.anomaly_observer import detect_anomalies
   for f in detect_anomalies(emit_events=False):
       print(f"[{f.severity}] {f.rule}: {f.title}")
   ```

---

## What this unlocks — the road from here

Phase O2 is the **observability foundation** for everything that follows:
- **O3 channel simulators** (v10.477-479) will emit channel events that flow into the same lineage/replay/anomaly pipeline
- **O4 time evolution** (v10.480-481) will track macro-event impacts via the heatmap aggregations
- **O5 chaos** (v10.482) will inject failures and use the anomaly observer to verify recovery
- **O6 AI evolution lab** (v10.483-484) will use `model_stats` as the baseline for drift detection
- **O7 training arena** (v10.485-486) will replay real production timelines for trainee scoring

Roadmap:
- ✅ **v10.473** O1 Wiring
- ✅ **v10.474** O8 Isolation
- ✅ **v10.475** O2-A Telemetry (event bus + lineage + replay)
- ✅ **v10.476** O2-B Observability (AI + heatmaps + anomalies + API telemetry)
- ⏭️ **v10.477** O3-A — Channel simulators batch 1 (5 of 7: RTGS / SWIFT / ATM / USSD / M-Pesa)
- **v10.478-479** O3-B/C — Remaining channels (KIC / Cards) + scenario library expansion → 100+
- **v10.480-481** O4 — Time evolution + macro simulation
- **v10.482** O5 — Chaos engineering
- **v10.483-484** O6 — AI/ML/LLM evolution lab
- **v10.485-486** O7 — Training arena
- **v10.487** Olympic-grade certification
- **v10.488+** Track C — React facelift

---

## 🏥 Patient status

Nervous system **fully online**. Every nerve transmits. Every AI decision speaks. Every bottleneck visible. Every anomaly auto-flagged. Every API call timed.

Tell me **"continue"** for v10.477 — Phase O3-A (channel simulators batch 1: RTGS + SWIFT + ATM + USSD + M-Pesa).
