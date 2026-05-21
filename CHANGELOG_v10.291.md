# Changelog — v10.291 CIMS Batch 2: Process Intelligence & Prediction

**Date:** 2026-05-08
**Phase:** 2B
**Audit:** 183/183 gates PASS = 100.0%
**G162 Rebase:** none — engines are pure operations logic, no new
CBK/Kenya/KES/Ecobank/FLEXCUBE/KRA tokens introduced. Baseline holds
at 3967.

---

## Summary

Second of 4 CIMS arc batches. Activates 4 standards (#169, #170, #174,
#175) covering the intelligence and prediction layer of the Customer
Instructions Management System: how instruction journeys are observed
and analysed (process intel + digital twin), how customer abandonment
is predicted and prevented (dropout prevention), how the system
recommends what the customer should do next (NBA), and how exceptions
are tracked through their lifecycle with SLA discipline (automated
exception management).

7 active standards remain planned in the CIMS arc:
  • v10.292 Batch 3 (#171, #172, #176, #178 — Compliance & Audit)
  • v10.293 Batch 4 (#177, #179, #180 — Closure)

---

## Standards activated

| Standard | Name | Engine |
|----------|------|--------|
| #169 | Process Intelligence & Digital Twin | `cims_process_intelligence` |
| #170 | Predictive Dropout Prevention | `cims_dropout_prevention` |
| #174 | Next Best Action for Instructions | `cims_next_best_action` |
| #175 | Automated Exception Management | `cims_exception_management` |

---

## Files changed

  • utils/cims_process_intelligence.py — already shipped at session
    open; verified to match #169 spec (PROCESS_INSTANCE_STATES (5)
    Rule 4 + STEP_EVENT_TYPES (5) + STEP_OUTCOMES (4) +
    BOTTLENECK_TYPES (4) + percentile=95 + retry_threshold=3 +
    refresh=60s).
  • utils/cims_dropout_prevention.py — NEW. Cat D Rule 7 scaffold:
    rule_based deterministic scoring + optional ml_score_fn factory
    hook. DROPOUT_RISK_TIERS (4: LOW/MEDIUM/HIGH/CRITICAL with
    thresholds 30/60/80) + SIGNAL_STATES (5) Rule 4 with RESOLVED +
    FALSE_POSITIVE terminals + INTERVENTION_TYPES (6) +
    INTERVENTION_OUTCOMES (5) + DROPOUT_RISK_FACTOR_WEIGHTS_PCT
    (SESSION_DURATION=25, CHANNEL_HOPS=20, PROCESS_DEVIATION=20,
    HISTORICAL_ABANDONMENT=25, INSTRUCTION_COMPLEXITY=10; sum=100) +
    horizon=4h + cooldown=24h + SPEC_DEVIATION_NOTE module-level
    constant.
  • utils/cims_next_best_action.py — NEW. Cat D Rule 7 scaffold:
    rule_based deterministic ranking + optional ml_rank_fn factory
    hook. NBA_ACTION_TYPES (8: COMPLETE_INSTRUCTION/RESUME_LATER/
    ESCALATE_TO_RM/SWITCH_CHANNEL/ADD_DOCUMENT/CONTACT_SUPPORT/
    CANCEL_INSTRUCTION/REVIEW_DETAILS) + NBA_RULE_STATES (4) Rule 4
    (DEPRECATED→ARCHIVED only) + RECOMMENDATION_OUTCOMES (5:
    ACCEPTED/REJECTED/IGNORED/OVERRIDDEN/EXPIRED) +
    ACTION_PRIORITY_TIERS (4: URGENT/HIGH/NORMAL/LOW) +
    NBA_RULE_FACTOR_WEIGHTS_PCT (INSTRUCTION_TYPE_FIT=30,
    SESSION_STATE=20, DROPOUT_RISK=25, CUSTOMER_HISTORY=15,
    CHANNEL_PREFERENCE=10; sum=100) + top_n=3 + ttl=4h +
    SPEC_DEVIATION_NOTE module-level constant.
  • utils/cims_exception_management.py — NEW. EXCEPTION_SEVERITIES
    (4) + EXCEPTION_STATES (6: OPEN/ASSIGNED/IN_PROGRESS/ESCALATED/
    RESOLVED/CANCELLED) Rule 4 with RESOLVED + CANCELLED terminals +
    ESCALATION_TARGETS (5: TEAM_LEAD/OPERATIONS_HEAD/RM/
    COMPLIANCE_OFFICER/CCO) + RESOLUTION_OUTCOMES (5) +
    EXCEPTION_CATEGORIES (8: DATA_QUALITY/SLA_BREACH/
    MANUAL_REVIEW_NEEDED/SYSTEM_TIMEOUT/COMPLIANCE_FLAG/
    IDENTITY_MISMATCH/DOCUMENT_MISSING/CHANNEL_FAILURE) +
    SLA_TARGETS_HOURS (LOW=72, MEDIUM=24, HIGH=8, CRITICAL=2) +
    auto_escalation_high=4h + reassignment_limit=3.
  • pages/106_cims_process.py — NEW. 7-tab cockpit covering all 4
    engines: process twins, step events + bottlenecks, dropout
    signals + Cat D scoring, interventions + outcomes + save-rate
    metrics, NBA ranking + recommendation outcomes + acceptance
    metrics, exception lifecycle + escalations + open list,
    resolution + SLA breach report. Uses
    `require_access("operations.cims_process")` and `audit_log()`
    after every write.
  • scripts/audit.py — added gate_cims_intelligence_prediction_
    registered() (G183) locking all 4 engines + every enum tuple +
    every weights dict + every default constant + Rule 4 terminals
    byte-for-byte. Registered G183 in GATES tuple.
  • pages/7_admin.py — added Tier 51 with all 4 engine entries.
  • pages/_manifest.json — added 106_cims_process.py entry with all
    7 required fields (department_primary=operations,
    module_path=operations.cims_process,
    secondary_visibility=__all_admins__, title, icon, description,
    current_module_key).
  • utils/standards_registry.py — flipped #169, #170, #174, #175 to
    status="active", implementation_batch="v10.291".
  • CHANGELOG_v10.291.md — this file.

---

## CIMS arc progress

| Batch | Version | Standards | Status |
|-------|---------|-----------|--------|
| 1 | v10.290 | #166, #167, #168, #173 | shipped |
| 2 | v10.291 | #169, #170, #174, #175 | **shipped** |
| 3 | v10.292 | #171, #172, #176, #178 | planned |
| 4 | v10.293 | #177, #179, #180 | planned |

CIMS arc 8/15 complete after this drop.

---

## Audit gates

| Gate | Status | Notes |
|------|--------|-------|
| G160 (manifest) | PASS | 110 pages, 16 departments, all required fields present |
| G162 (tenant) | PASS | held at 3967 — no new tenant tokens |
| G177 (imports) | PASS | canonical imports verified |
| G182 (CIMS B1) | PASS | locked from v10.290 |
| G183 (CIMS B2) | PASS | NEW — 4 engines registered, all enums + constants byte-for-byte |

---

## Platform state

  • Audit: **183/183 gates = 100.0% PASS**
  • Standards active: **323/330** (4 newly active: #169, #170, #174, #175)
  • Standards remaining: 7 (all CIMS — 4 in Batch 3, 3 in Batch 4)
  • Audit gate count: G1 → G183 (183 total)
  • Engine Hub: 51 tiers
  • Pages: 110 (manifest entries match)

---

## Cluster invariants verified

  ✅ One ZIP per cluster (4 engines + 1 page + audit + admin + manifest + standards + changelog)
  ✅ All audit_log() calls after write operations
  ✅ All page-level require_access() uses dotted manifest path
  ✅ Canonical imports throughout: `from utils.core_audit import audit_log` and `from pages._access import require_access`
  ✅ ≤7 tabs per page (page 106 uses exactly 7)
  ✅ Standards registry status="active" + batch="v10.291" for all 4
  ✅ G183 added linearly (no gate ID reuse)
  ✅ Tier 51 added in admin (no tier reuse)
  ✅ Manifest entry for page 106 has all 7 required fields
