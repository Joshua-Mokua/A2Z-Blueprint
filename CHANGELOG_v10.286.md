# Changelog — v10.286 Analytics Hub Workbench + Reports

**Date:** 2026-05-08
**Phase:** 2B (open)
**Audit:** 178/178 gates PASS = 100.0%
**G162 Rebase:** 3901 → 3910 (+9 CBK; rationale: analytics modules reference CBK Cybersecurity Guidance and CBK PG-series scheduling cadences)

---

## Summary

First Phase 2B cluster. Two analytics_hub standards activated:

- **#286 Credit Analyst Workbench** — read-side composition over upstream credit + statement + bureau + affordability engines, with conflict reporting when sources disagree.
- **#287 Scheduled Reports & Alerts** — schedule + alert rule + delivery registry across email, Slack, Teams, and download links.

20 active standards remain planned after this batch (CIMS arc 15, Analytics Hub NLQ/Anomaly/Export 3, Compliance Dashboard 1, Trade Finance Mobile 1).

---

## Standards activated

| ID      | Name                            | Subcategory     | Risk |
|---------|---------------------------------|-----------------|------|
| ENH-286 | Credit Analyst Workbench        | analytics_hub   | Cat C |
| ENH-287 | Scheduled Reports & Alerts      | analytics_hub   | Cat C |

Both flipped status="active", implementation_batch="v10.286".

---

## Engine modules

### `utils/analytics_credit_workbench.py` (#286)

`CreditWorkbenchEngine` with sessions / views / pulls / notes registry.

Byte-for-byte invariants:
- `WORKBENCH_SESSION_STATES` (5: OPEN, IN_REVIEW, ESCALATED, COMPLETED, CANCELLED) — Rule 4 (COMPLETED + CANCELLED terminal)
- `DATA_SOURCES` (6: CREDIT_DECISION_ENGINE, STATEMENT_ANALYZER, CREDIT_BUREAU, AFFORDABILITY_ENGINE, COLLATERAL_REGISTRY, DOCUMENT_VERIFIER)
- `VIEW_TYPES` (5: SUMMARY, DETAIL, COMPARISON, TIMELINE, CONFLICT)
- `NOTE_CATEGORIES` (5: OBSERVATION, CONCERN, FOLLOW_UP, RECOMMENDATION, DECISION_RATIONALE)
- `DEFAULT_SESSION_TIMEOUT_HOURS = 24`
- `DEFAULT_DATA_PULL_CACHE_MINUTES = 15`

Key methods:
- `register_workbench_session`, `transition_session_state`
- `register_workbench_view`
- `record_data_pull`, `record_analyst_note`
- `workbench_summary(session_id)` — returns state, source coverage, notes by category
- `conflict_report(session_id)` — surfaces when upstream sources return different `snapshot_decision` values for the same customer

### `utils/analytics_scheduled_reports.py` (#287)

`ScheduledReportsEngine` with schedule + alert + delivery registry.

Byte-for-byte invariants:
- `DELIVERY_CHANNELS` (4: EMAIL, SLACK, TEAMS, DOWNLOAD_LINK)
- `SCHEDULE_FREQUENCIES` (6: HOURLY, DAILY, WEEKLY, MONTHLY, QUARTERLY, ON_DEMAND)
- `SCHEDULE_STATES` (4: ACTIVE, PAUSED, FAILED, ARCHIVED) — Rule 4 (ARCHIVED terminal)
- `ALERT_TRIGGER_TYPES` (5: THRESHOLD_BREACH, TREND_DEVIATION, ANOMALY, MISSING_DATA, MANUAL)
- `ALERT_STATES` (4: ACTIVE, SILENCED, ACKNOWLEDGED, RESOLVED) — Rule 4 (RESOLVED terminal; ACKNOWLEDGED can only go to RESOLVED)
- `DELIVERY_STATES` (4: QUEUED, SENT, DELIVERED, FAILED)
- `DEFAULT_DELIVERY_TIMEOUT_SECONDS = 60`
- `DEFAULT_RETRY_LIMIT = 3`

Key methods:
- `register_schedule`, `transition_schedule_state`
- `register_alert_rule`, `transition_alert_state`
- `record_delivery`
- `delivery_metrics(days=30)` — total / delivered / failed / per-channel breakdown
- `schedules_due(within_minutes=60)` — sorted by `next_run_at`

---

## Page

### `pages/101_analytics_workbench.py`

6 tabs (G4-compliant ≤7):
1. Workbench session — open + transitions + view registration + summary
2. Data pulls + conflicts — record snapshots, run conflict report
3. Analyst notes — captured by category, optionally linked to a pull
4. Schedules — register, transition state, list due
5. Alerts — register, transition state
6. Deliveries — record, metrics with per-channel breakdown

Canonical imports throughout (G177 enforces):
```python
from utils.core_audit import audit_log
from pages._access import require_access
require_access("shared.analytics_workbench")
```

`audit_log()` calls use canonical signature `(action, username, module)` on every write surface.

---

## Audit gate

### G178 — `gate_analytics_workbench_registered`

Locks both engines + every enum invariant + spec constants byte-for-byte. Any future drift on the Rule 4 terminal states, channel sets, or default constants fails the build.

Checks:
1. Both modules import and expose their named engine classes.
2. All 9 enum tuples byte-for-byte against the spec above.
3. ALLOWED_SESSION_TRANSITIONS["COMPLETED"]/["CANCELLED"] are () (Rule 4).
4. ALLOWED_SCHEDULE_TRANSITIONS["ARCHIVED"] is () (Rule 4).
5. ALLOWED_ALERT_TRANSITIONS["RESOLVED"] is () (Rule 4).
6. All 6 default spec constants match.
7. ENH-286 and ENH-287 are active and tagged v10.286.
8. Page 101 exists on disk.

---

## G162 ratchet

```
Before:    3901 (established_in v10.282)
After:     3910 (established_in v10.286)
Delta:     +9 (all CBK)
Scope history entries: 40
```

The 9 new CBK tokens come from the analytics modules' regulatory framing — CBK Cybersecurity Guidance bindings on the schedule/alert state machines, and CBK PG-series scheduling cadence in the docstring context. No FLEXCUBE, Kenya, or Ecobank tokens added.

---

## Tier registration

`Tier 46 — Analytics Hub: Workbench + Reports (v10.286, Phase 2B)` added to `pages/7_admin.py` with both engines registered.

---

## Manifest entry

`101_analytics_workbench.py` registered with all 7 required fields:
- `department_primary`: "shared"
- `module_path`: "shared.analytics_workbench"
- `secondary_visibility`: ["__all_admins__"]
- `title`: "Analytics Hub — Workbench & Reports"
- `icon`: "📊"
- `description`: full Phase 2B v10.286 description
- `current_module_key`: "analytics_workbench"

G160 enforces; G177 confirms `require_access("shared.analytics_workbench")` resolves.

---

## Files in this release

```
utils/analytics_credit_workbench.py            NEW (#286, ~370 lines)
utils/analytics_scheduled_reports.py           NEW (#287, ~390 lines)
utils/standards_registry.py                    flipped ENH-286, ENH-287 to active
scripts/audit.py                               +G178 gate_analytics_workbench_registered
pages/7_admin.py                               +Tier 46
pages/101_analytics_workbench.py               NEW (6-tab cockpit)
pages/_manifest.json                           +101 entry
data/audit_baselines.json                      g162 rebase to 3910
CHANGELOG_v10.286.md                           NEW (this document)
```

---

## Audit summary

```
  Score: 178/178 gates = 100.0% — PASS
```

Phase 2B opens cleanly. Next batch (v10.287) closes the remaining Analytics Hub extensions (#288 NLQ + #289 Anomaly + #290 Data Export).
