# A2Z Blueprint MIS 360 — AI Governance

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md`)
**Status:** `canonical`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 5)
**Last updated:** 2026-05-22
**Owner:** ML Governance / Model Risk
**Authoritative sources:**
- `utils/model_governance.py`, `utils/model_governance_runtime.py`
- `utils/mlops_*.py` family (6 modules)
- `utils/ai_explainability.py`, `utils/ai_underwriting.py`, `utils/fairness_testing.py`

**Machine-readable equivalent:** `AI_GOVERNANCE.json`

---

## Purpose

This document declares the governance regime for every machine-learning model, AI agent, and predictive engine in the A2Z system. ML models make decisions about customers (credit, churn, segmentation), staff (performance, wellness), and the bank (anomaly detection, forecasting). Without governance, those decisions are opaque, unaccountable, and regulatorily exposed.

Per Article IX of `SYSTEM_CONSTITUTION.md`: models must be registered before deployment; predictions emit adjudication log entries; rollouts go through the AB harness; retraining is scheduler-controlled; human-impact models require explainability + fairness testing.

This artifact also resolves Wave 3 unknowns:
- `utils/agents/` — AI agent infrastructure (`gate_v10484_o6b_agent_infrastructure`, G370)
- `utils/ml/` — ML model definitions and evolution lab (`gate_v10483_o6a_ml_evolution_lab`, G369)

---

## Doctrine

**AI1 — No deployment without registration.** Every model that influences a production decision must exist in `mlops_model_registry` with a model card before its predictions reach a user or workflow.

**AI2 — Every prediction is adjudicated.** Predictions emit entries to `mlops_adjudication_log`. The log is the canonical trail for "why did the system do X?"

**AI3 — Rollouts are AB-controlled.** New models or model versions don't replace incumbents; they enter an AB cohort via `mlops_ab_harness`. Promotion to full traffic requires evidence.

**AI4 — Human-impact decisions require explainability + fairness.** If a model affects a person (credit, employment, segmentation), it must support `ai_explainability.explain(prediction)` and pass `fairness_testing.assess(model)`.

**AI5 — Drift is detected, not suspected.** `gate_anti_drift_completion_floor` (scripts/audit.py:18223) enforces threshold-based drift detection. Models drifting below the floor are taken out of service.

**AI6 — Retraining is scheduled, not ad-hoc.** Only `mlops_retraining_scheduler` may trigger retraining. Direct retraining calls outside the scheduler are violations.

**AI7 — Agents are bounded.** AI agents (`utils/agents/`) have declared scopes, declared tools, declared escalation paths. They cannot take actions outside their declared boundary.

---

## The AI/ML organ family

### Model lifecycle infrastructure

| Module | Responsibility | Canonical interface |
|---|---|---|
| `utils/model_governance.py` | Top-level governance contracts | Model registration, lifecycle state |
| `utils/model_governance_runtime.py` | Runtime governance enforcement | Pre-prediction checks, post-prediction logging |
| `utils/mlops_model_registry.py` | Model registry (versioned) | `register_model`, `get_model`, `list_models`, `retire_model` |
| `utils/mlops_model_card_composer.py` | Model card generation | `compose_card(model_id)` → structured documentation |
| `utils/mlops_persistence.py` | Model artifact persistence | Load/save model weights, configs |
| `utils/mlops_ab_harness.py` | A/B testing infrastructure | `start_experiment`, `record_outcome`, `assess_winner` |
| `utils/mlops_adjudication_log.py` | Prediction adjudication log | `log_prediction`, `log_decision`, append-only |
| `utils/mlops_retraining_scheduler.py` | Retraining trigger | `schedule_retrain`, `execute_retrain` |

### Explainability & fairness

| Module | Responsibility |
|---|---|
| `utils/ai_explainability.py` | Per-prediction explanations |
| `utils/fairness_testing.py` | Bias detection, fairness metrics |

### Production AI engines

| Module | Domain | Decision type |
|---|---|---|
| `utils/ai_underwriting.py` | Credit underwriting | Approve / decline / refer |
| `utils/credit_alt_scoring.py` | Alternative credit scoring | Score (0-100) |
| `utils/credit_risk_scoring.py` | Credit risk scoring | Risk grade |
| `utils/decline_prediction.py` | Decline prediction | Likely-to-decline flag |
| `utils/churn_prediction.py` | Churn prediction | Churn probability |
| `utils/cross_sell_bandit.py` | Cross-sell (RL bandit) | Product recommendation |
| `utils/cross_sell_nba.py` | Next best action | Action recommendation |
| `utils/customer_segmentation.py` | Customer segmentation | Segment label |
| `utils/predictive_performance.py` | Staff performance prediction | EOM achievement probability |
| `utils/behavioral_anomaly_detection.py` | Behavioral anomaly | Anomaly score + flag |
| `utils/analytics_anomaly_detection.py` | Statistical anomaly | Anomaly score |

### `utils/ml/` subdirectory (resolves OI-23 for ml/)

Per `gate_v10483_o6a_ml_evolution_lab` (G369 — scripts/audit.py:56601):

`utils/ml/` is the **ML evolution lab** — model definitions, training scripts, and experimentation infrastructure separated from production runtime.

Expected structure (hypothesis pending OI-45):
- Model class definitions (per algorithm family)
- Feature engineering pipelines
- Training scripts
- Notebook-replay scripts
- Hyperparameter search infrastructure

**OI-45** — Joshua to provide `dir utils\ml /b` for explicit enumeration.

### `utils/agents/` subdirectory (resolves OI-23 for agents/)

Per `gate_v10484_o6b_agent_infrastructure` (G370 — scripts/audit.py:56886):

`utils/agents/` is the **AI agent infrastructure** — autonomous or semi-autonomous agents that make multi-step decisions within bounded scopes.

Known agent module: `utils/treasury_agents.py` (referenced in utils inventory).

Expected agent structure (hypothesis pending OI-46):
- Agent definitions (treasury agent, customer service agent, compliance agent)
- Tool registry (what each agent can call)
- Scope definitions (what each agent can affect)
- Escalation paths (when human-in-the-loop required)
- Decision audit trail

**OI-46** — Joshua to provide `dir utils\agents /b` for explicit enumeration.

---

## Model lifecycle states

Every model in `mlops_model_registry` transitions through:

| State | Meaning | Permitted actions |
|---|---|---|
| `proposed` | Model defined, not yet trained | Train, modify |
| `training` | Training in progress | Monitor, abort |
| `evaluation` | Trained, undergoing evaluation | Test, profile, fairness-test |
| `ab_candidate` | Approved for A/B harness | Receive cohort traffic via ab_harness |
| `production_primary` | Serving primary traffic | Predict, log, monitor for drift |
| `production_shadow` | Serving in parallel with primary, predictions logged but not used | Compare against primary |
| `drifted` | Below `gate_anti_drift_completion_floor` threshold | Retrain or retire |
| `retired` | Removed from production | Read-only historical inspection |

Transitions are append-only entries in the registry. No model "skips" states — proposed → training → evaluation → ab_candidate → production_primary is the canonical path.

---

## Model card contract

Every registered model has a **model card** (per `mlops_model_card_composer`). Canonical schema:

```json
{
  "model_id": "credit_alt_scoring_v3",
  "version": "3.0.2",
  "domain": "credit",
  "purpose": "Alternative credit scoring for thin-file applicants",
  "owner": "Credit Risk team",
  "trained_on": {
    "dataset": "credit_applications_2025_2026",
    "rows": 245000,
    "features": 47,
    "training_start": "2026-02-15",
    "training_end": "2026-02-18"
  },
  "algorithm": "XGBoost",
  "hyperparameters": { /* ... */ },
  "performance": {
    "auc_roc": 0.872,
    "precision_at_recall_0.8": 0.74,
    "calibration_score": 0.91
  },
  "fairness_assessment": {
    "tested_on": ["gender", "age_band", "branch_region"],
    "max_disparity": 0.04,
    "passed": true
  },
  "explainability": {
    "method": "SHAP",
    "top_features": ["account_tenure_months", "avg_balance_3m", "transaction_velocity"]
  },
  "deployment": {
    "state": "production_primary",
    "deployed_at": "2026-03-01T08:00:00Z",
    "deployed_by": "william001",
    "ab_cohort": null
  },
  "drift_thresholds": {
    "auc_floor": 0.82,
    "precision_floor": 0.68,
    "monitoring_window_days": 14
  },
  "retired": null
}
```

`gate_model_governance_engines_implemented` (scripts/audit.py:14969) enforces model card completeness.

---

## A/B harness contract

`utils/mlops_ab_harness.py` controls model rollout. Lifecycle:

```
new model v4 → register as proposed
       ↓
train, evaluate, fairness-test → eligible
       ↓
ab_harness.start_experiment(
  primary=v3,
  candidate=v4,
  traffic_split=10,         # 10% to candidate
  duration_days=14,
  success_criteria={"auc_uplift": 0.02, "fairness_no_regression": True}
)
       ↓
both predict; outcomes captured
       ↓
ab_harness.assess_winner()
       ↓
if winner=v4: promote v4 to production_primary, retire v3
if winner=v3: retire v4 as proposed
if inconclusive: extend or terminate
```

Promotion to `production_primary` is logged as an event (`mlops.model.deployed`) and creates an entry in REVIVAL_LEDGER.

---

## Adjudication log

`mlops_adjudication_log` is **the** canonical record of "why did the system make decision X?"

Every model prediction emits:

```json
{
  "timestamp": "2026-05-22T13:30:45.012Z",
  "model_id": "credit_alt_scoring_v3",
  "model_version": "3.0.2",
  "input_record_id": "loan_application_LA-2026-447283",
  "prediction": {
    "score": 73,
    "decision": "approve_with_conditions",
    "confidence": 0.84
  },
  "explanation": {
    "method": "SHAP",
    "top_contributors": [
      {"feature": "account_tenure_months", "value": 36, "contribution": 0.18},
      {"feature": "avg_balance_3m", "value": 145000, "contribution": 0.15},
      {"feature": "transaction_velocity", "value": 8.2, "contribution": -0.05}
    ]
  },
  "human_review": null,
  "outcome_recorded": null
}
```

The `human_review` and `outcome_recorded` fields are populated later (when a human reviews the decision and when the outcome is observable). This enables ground-truth learning and supervised retraining.

`mlops_persistence` retains adjudication logs **indefinitely** per regulatory requirement.

---

## Explainability requirements

Per AI4: human-impact models MUST support per-prediction explanations.

### Required for human-impact models

| Decision domain | Why explainability matters |
|---|---|
| Credit approval/decline | Regulatory (adverse action notices); customer right to know |
| Pricing | Customer trust, regulatory |
| Churn prediction (triggers outreach) | RM understanding why customer flagged |
| Customer segmentation | Treatment fairness |
| Wellness assessment | Subject's right to understand |

### Permitted methods

`ai_explainability.py` should support:

- **SHAP** — primary canonical method
- **LIME** — alternative local explanation
- **Counterfactuals** — "if X had been different, decision would have been Y"
- **Feature importance** — global model-level

### Forbidden patterns

- Black-box production models for human-impact decisions
- Post-hoc rationalization (generating explanations that don't reflect actual decision logic)
- Single-feature explanations when multi-feature interaction dominates

---

## Fairness testing

`utils/fairness_testing.py` is the canonical fairness assessor.

### Required dimensions

Every human-impact model is tested against:

| Dimension | Why |
|---|---|
| Gender | Regulatory + ethical |
| Age band | Age discrimination protection |
| Region / branch | Geographic equity |
| Segment | Cross-segment fairness |
| (Custom for Kenya context) | Per regulator requirement |

### Metrics

- **Demographic parity** — equal positive rate across groups
- **Equal opportunity** — equal true positive rate across groups
- **Calibration** — predicted probability matches actual rate across groups
- **Disparity ratio** — max(group_metric) / min(group_metric); target ≤ 1.2

Models exceeding disparity thresholds are blocked from promotion to `production_primary`.

---

## Drift detection

`gate_anti_drift_completion_floor` (scripts/audit.py:18223) enforces drift floors per the model card's `drift_thresholds`.

Drift triggers:
- AUC dropping below `auc_floor`
- Precision dropping below `precision_floor`
- Feature distribution shift > threshold
- Outcome distribution shift > threshold

When triggered:
1. Model state changes to `drifted`
2. Event published: `mlops.drift.detected`
3. Retraining scheduled via `mlops_retraining_scheduler`
4. If retraining doesn't recover within X days, model retired
5. Fallback model takes over

---

## Retraining policy

Only `utils/mlops_retraining_scheduler.py` may trigger retraining. Triggers:

| Trigger | Action |
|---|---|
| Scheduled cadence (e.g. quarterly) | Routine retrain |
| Drift detection | Emergency retrain |
| New data threshold (e.g. +50K new records) | Opportunistic retrain |
| Manual request via admin (logged) | Ad-hoc retrain |

Ad-hoc retrains require explicit admin authorization + audit event `API_MLOPS_RETRAIN_TRIGGERED` (new event TBD in TELEMETRY_MAP amendment).

---

## AI agent governance

Per AI7: agents are bounded. The agent contract:

```json
{
  "agent_id": "treasury_agent_v1",
  "purpose": "Treasury front-office advisory",
  "scope": {
    "domains": ["treasury", "fx", "money_market"],
    "data_read": ["data/treasury_*.json", "data/macro_state.json"],
    "data_write": [],
    "tools_allowed": ["forecast_yields", "compute_var", "recommend_position"],
    "actions_forbidden": ["execute_trade", "modify_limits", "approve_credit"]
  },
  "escalation": {
    "uncertainty_threshold": 0.5,
    "escalation_target": "Senior Manager Treasury",
    "stop_conditions": ["user_explicit_stop", "scope_violation_attempt"]
  },
  "audit": {
    "every_decision_logged": true,
    "log_target": "mlops_adjudication_log",
    "review_cadence_days": 30
  }
}
```

Agents that attempt actions outside their declared scope are **stopped** and the attempt is logged as a `mlops.agent.scope_violation` event. Repeated violations remove the agent from production.

---

## Audit gate ladder

| Gate | ID | Line | Purpose |
|---|---|---|---|
| `gate_model_governance_engines_implemented` | — | 14969 | Foundation modules exist |
| `gate_ml_governance_arc_closed` | — | 17765 | ML governance arc complete |
| `gate_ml_governance_arc_ui_integrated` | — | 17977 | UI integration complete |
| `gate_ml_governance_cross_platform_wiring` | — | 18100 | Cross-platform wiring |
| `gate_anti_drift_completion_floor` | — | 18223 | Drift floor enforced |
| `gate_cross_sell_bandit_pilot_implemented` | — | 15376 | RL bandit pilot |
| `gate_v10483_o6a_ml_evolution_lab` | G369 | 56601 | ML evolution lab (utils/ml/) |
| `gate_v10484_o6b_agent_infrastructure` | G370 | 56886 | Agent infrastructure (utils/agents/) |
| `gate_v10476_o2b_ai_heatmap_anomaly_telemetry` | G362 | 54658 | AI heatmap + anomaly telemetry |

---

## Stage C gates planned

| Gate | Purpose | Severity |
|---|---|---|
| `gate_no_unregistered_model_in_production` | Verify every prediction site loads from mlops_model_registry | CRITICAL |
| `gate_human_impact_model_has_explainability` | Every credit/churn/wellness model has explanation method | HIGH |
| `gate_human_impact_model_passes_fairness` | Disparity ratio ≤ 1.2 for required dimensions | HIGH |
| `gate_adjudication_log_complete` | Every prediction has adjudication log entry | HIGH |
| `gate_agent_scope_declared` | Every agent in utils/agents/ has declared scope file | CRITICAL |
| `gate_ab_harness_used_for_promotion` | No model goes to production without ab_harness validation | HIGH |
| `gate_retraining_only_via_scheduler` | No retraining calls outside mlops_retraining_scheduler | HIGH |

---

## Open items

| ID | Title | Resolution wave |
|---|---|---|
| OI-45 | Enumerate `utils/ml/` contents | Follow-up batch (Joshua dir) |
| OI-46 | Enumerate `utils/agents/` contents | Follow-up batch |
| OI-47 | Model card schema canonical declaration | Stage C |
| OI-48 | Agent scope declaration schema | Stage C |
| OI-49 | Adjudication log retention policy (current is "indefinite"; regulator may require specifics) | Stage C |
| OI-50 | Per-model fairness dimensions (some models may need additional dims beyond gender/age/region) | Per-model registration |

---

**End of AI_GOVERNANCE.md**
