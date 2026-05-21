# Changelog — v10.287 Analytics Hub: NLQ + Anomaly + Export

**Date:** 2026-05-08
**Phase:** 2B
**Audit:** 179/179 gates PASS = 100.0%
**G162 Rebase:** 3910 → 3927 (+13 CBK, +4 Kenya; rationale: Data Export module locks DPA Kenya 2019 + CBK Cybersecurity Guidance as named references)

---

## Summary

Closes the Analytics Hub extensions arc with three engines covering
natural language query, anomaly detection, and data export — the
latter with PII tier controls and named-approver requirements for
CRITICAL_PII bulk exports. 17 active standards remain planned after
this batch (CIMS arc 15, Trade Finance Mobile 1, Compliance Dashboard 1).

---

## Standards activated

| ID      | Name                                | Subcategory     | Risk |
|---------|-------------------------------------|-----------------|------|
| ENH-288 | Natural Language Query (NLQ)        | analytics_hub   | Cat C |
| ENH-289 | Anomaly Detection & Alerting        | analytics_hub   | Cat C |
| ENH-290 | Data Export & Integration Hub       | analytics_hub   | Cat C |

All three flipped status="active", implementation_batch="v10.287".

---

## Engine modules

### `utils/analytics_nlq.py` (#288)

`NLQEngine` — natural-language → SQL request lifecycle registry.
Diagnostic only (Rule 7) — does not execute SQL itself; the
SAFETY_REVIEW state blocks DDL/DML against vetted SELECT-only views.

Byte-for-byte invariants:
- `QUERY_REQUEST_STATES` (6: SUBMITTED, TRANSLATED, SAFETY_REVIEW, APPROVED, EXECUTED, REJECTED) — Rule 4
- `QUERY_DOMAINS` (5: CUSTOMERS, ACCOUNTS, TRANSACTIONS, REPORTS, AGGREGATES)
- `SAFETY_VERDICTS` (4: SAFE, UNSAFE_DDL, UNSAFE_DML, UNSAFE_SCOPE)
- `EXECUTION_OUTCOMES` (4: SUCCESS, EMPTY, ERROR, TIMEOUT)
- `DEFAULT_QUERY_TIMEOUT_SECONDS = 30`
- `DEFAULT_MAX_ROWS_RETURNED = 10000` (enforced as a hard cap on outcome record)
- `DEFAULT_TRANSLATION_RETRY_LIMIT = 3`

### `utils/analytics_anomaly_detection.py` (#289)

`AnomalyDetectionEngine` — detection rule + observation + classification registry. Composes upstream risk + revenue assurance anomaly engines (#241–#248).

Byte-for-byte invariants:
- `DETECTION_METHODS` (5: THRESHOLD, Z_SCORE, MOVING_AVERAGE, ISOLATION_FOREST, MANUAL)
- `RULE_STATES` (4: ACTIVE, PAUSED, DEPRECATED, ARCHIVED) — Rule 4 (DEPRECATED → ARCHIVED only)
- `ANOMALY_SEVERITIES` (4: LOW, MEDIUM, HIGH, CRITICAL)
- `ANOMALY_STATES` (5: OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE, SUPPRESSED) — Rule 4 (RESOLVED, FALSE_POSITIVE, SUPPRESSED all terminal)
- `ANOMALY_CLASSIFICATIONS` (5: DATA_QUALITY, SEASONALITY, GENUINE_ANOMALY, POLICY_BREACH, UNCLASSIFIED)
- `DEFAULT_DETECTION_INTERVAL_MINUTES = 15`
- `DEFAULT_SEVERITY_ESCALATION_HOURS = 4`

### `utils/analytics_data_export.py` (#290)

`DataExportEngine` — export request + endpoint + execution registry. PII tier controls and bytes-per-export hard cap.

Byte-for-byte invariants:
- `EXPORT_FORMATS` (5: CSV, XLSX, JSON, PARQUET, XML)
- `EXPORT_REQUEST_STATES` (5: REQUESTED, APPROVED, IN_PROGRESS, COMPLETED, CANCELLED) — Rule 4
- `PII_TIERS` (5: NONE, LOW, MEDIUM, HIGH_PII, CRITICAL_PII)
- `INTEGRATION_TYPES` (5: REGULATORY_PORTAL, DATA_WAREHOUSE, BI_TOOL, PARTNER_API, INTERNAL)
- `EXECUTION_OUTCOMES` (4: SUCCESS, PARTIAL, FAILED, CANCELLED)
- `DEFAULT_EXPORT_TIMEOUT_SECONDS = 600`
- `DEFAULT_RETENTION_DAYS = 30`
- `DEFAULT_MAX_BYTES_PER_EXPORT = 5368709120` (5 GiB; enforced)
- `CBK_DPA_KENYA_REFERENCE = "Data Protection Act 2019"`
- `CBK_REGULATORY_REFERENCE = "CBK Cybersecurity Guidance"`

CRITICAL_PII guard: APPROVED transition requires a non-empty reason. The cockpit additionally surfaces `pii_critical_pending_review()` so DPO sees outstanding items.

---

## Page

### `pages/102_analytics_advanced.py`

7 tabs (right at G4 ceiling, planned upfront):
1. NLQ submit + lifecycle
2. NLQ safety + outcomes
3. Anomaly rules
4. Anomaly observations + classification + transitions + high-severity-open list
5. Export requests + state transitions + execution + CRITICAL_PII pending list
6. Integration endpoints
7. Metrics dashboard (NLQ + Anomaly + Export side-by-side)

Canonical imports throughout (G177):
```python
from utils.core_audit import audit_log
from pages._access import require_access
require_access("shared.analytics_advanced")
```

---

## Audit gate

### G179 — `gate_analytics_advanced_registered`

Locks 3 engines + 19 enum tuples + 9 default constants + 2 regulatory reference strings byte-for-byte.

---

## G162 ratchet

```
Before:    3910 (established_in v10.286)
After:     3927 (established_in v10.287)
Delta:     +17 (CBK +13, Kenya +4)
Scope history entries: 41
```

The increase comes from the Data Export module's two regulatory reference constants (DPA Kenya 2019 + CBK Cybersecurity Guidance) being echoed in the audit gate, the cockpit caption, and the module docstrings — plus the NLQ/anomaly modules carrying CBK Cybersecurity context in their docstrings and state-machine framing.

---

## Tier registration

`Tier 47 — Analytics Hub: NLQ + Anomaly + Export (v10.287, Phase 2B)` added to `pages/7_admin.py` with all three engines documented.

---

## Manifest entry

`102_analytics_advanced.py` registered with all 7 required fields:
- `module_path`: "shared.analytics_advanced"
- `current_module_key`: "analytics_advanced"
- icon "🧠"

---

## Files in this release

```
utils/analytics_nlq.py                          NEW (#288)
utils/analytics_anomaly_detection.py            NEW (#289)
utils/analytics_data_export.py                  NEW (#290)
utils/standards_registry.py                     flipped 288/289/290 active
scripts/audit.py                                +G179 gate_analytics_advanced_registered
pages/7_admin.py                                +Tier 47
pages/102_analytics_advanced.py                 NEW (7-tab cockpit)
pages/_manifest.json                            +102 entry
data/audit_baselines.json                       g162 rebase to 3927
CHANGELOG_v10.287.md                            NEW (this document)
```

---

## Audit summary

```
  Score: 179/179 gates = 100.0% — PASS
```

Analytics Hub is now complete (10/10 standards #281–#290 all active). Remaining Phase 2B: 17 standards — CIMS arc (15), Trade Finance Mobile (1), Compliance Dashboard (1).

Next batch: **v10.288 — Compliance Dashboard cockpit (#200, lone)**.
