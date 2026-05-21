# Changelog — v10.281 IT/Digital Foundation pt 1

**Date:** 2026-05-08
**Phase:** 2A — Active-standards expansion
**Cluster:** IT/Digital Foundation pt 1 (Standards #291–#295)
**Audit:** 174/174 gates PASS = 100.0%
**G162 Rebase:** 3818 → 3846 (+28)

---

## Summary

Phase 2A v10.281 ships the **IT/Digital Foundation pt 1 cluster** —
5 engines covering 5 standards (#291–#295). Audience: CTO, CIO,
SRE, security, compliance.

This batch establishes the operational backbone for the platform:
ITIL v4 ITSM (incidents, problems, changes, assets, knowledge),
cloud-native architecture with multi-cloud portability tracking,
SLI/SLO/error-budget observability, CBK-compliant disaster
recovery and business continuity, and an API gateway with
developer portal and rate-limit management.

This is the **18th closed cluster** in Phase 2A and the **78th
consecutive clean batch** since v10.193. ENH-294 is the cluster's
sole Category B (regulatory) standard — its `CBK Cybersecurity
Guidance` binding is locked under G174 byte-for-byte.

---

## Standards delivered

| Standard | Title                                          | Engine                   |
|----------|------------------------------------------------|--------------------------|
| ENH-291  | IT Service Management (ITSM) Framework         | it_itsm                  |
| ENH-292  | Cloud-Native & Container Architecture          | it_cloud_architecture    |
| ENH-293  | Observability & Monitoring                     | it_observability         |
| ENH-294  | Disaster Recovery & Business Continuity (Cat B)| it_disaster_recovery     |
| ENH-295  | API Gateway & Developer Portal                 | it_api_gateway           |

5 standards across 5 engines.

---

## Engines shipped

| #   | Module                       | Standard | Lines |
|-----|------------------------------|----------|-------|
| 1   | `utils/it_itsm.py`           | #291     | 458   |
| 2   | `utils/it_cloud_architecture.py` | #292 | 388   |
| 3   | `utils/it_observability.py`  | #293     | 442   |
| 4   | `utils/it_disaster_recovery.py` | #294  | 491   |
| 5   | `utils/it_api_gateway.py`    | #295     | 459   |

**Page:** `pages/96_it_digital_pt1.py` — 7 tabs, audit_log on every
write surface (G3 compliant), G4 compliant.

---

## Specification invariants locked under G174

- **ITSM_INCIDENT_PRIORITIES** (4): P1, P2, P3, P4
- **ITSM_INCIDENT_STATES** (5) Rule 4: OPEN, IN_PROGRESS, RESOLVED,
  CLOSED, CANCELLED — with re-open path RESOLVED → IN_PROGRESS
- **CHANGE_TYPES** (3): STANDARD, NORMAL, EMERGENCY
- **CHANGE_STATES** (6) Rule 4: PROPOSED, APPROVED, IN_IMPLEMENTATION,
  IMPLEMENTED, FAILED, ROLLED_BACK
- **ASSET_TYPES** (5): HARDWARE, SOFTWARE_LICENSE, NETWORK,
  CLOUD_RESOURCE, MOBILE_DEVICE
- **ASSET_STATES** (4): IN_USE, IN_STORAGE, RETIRED, LOST
- **KNOWLEDGE_ARTICLE_STATES** (3) Rule 4: DRAFT, PUBLISHED, ARCHIVED

- **CLOUD_PROVIDERS** (3): AWS, AZURE, GCP
- **CONTAINER_RUNTIMES** (3): KUBERNETES, DOCKER_SWARM, ECS
- **DEPLOYMENT_STRATEGIES** (5): BLUE_GREEN, CANARY, ROLLING,
  RECREATE, A_B_TEST
- **DEPLOYMENT_STATES** (5) Rule 4: PLANNED, DEPLOYED, ROLLING_BACK,
  ROLLED_BACK, RETIRED — with re-deploy path ROLLED_BACK → DEPLOYED
- **TWELVE_FACTOR_CRITERIA** (12): CODEBASE, DEPENDENCIES, CONFIG,
  BACKING_SERVICES, BUILD_RELEASE_RUN, PROCESSES, PORT_BINDING,
  CONCURRENCY, DISPOSABILITY, DEV_PROD_PARITY, LOGS, ADMIN_PROCESSES

- **SLI_TYPES** (5): LATENCY, AVAILABILITY, ERROR_RATE, THROUGHPUT,
  SATURATION
- **SLO_TIME_WINDOWS** (3): ROLLING_28_DAYS, CALENDAR_MONTH, QUARTER
- **SLO_STATES** (4) Rule 4: ACTIVE, PAUSED, MET, BREACHED
- **ERROR_BUDGET_POLICIES** (3): HALT_RELEASES, INCREASED_OVERSIGHT,
  ESCALATE_TO_LEADERSHIP
- DEFAULT_BUDGET_BURN_THRESHOLD_PCT = **50**

- **DR_PLAN_TIERS** (4): TIER_0_REALTIME, TIER_1_NEAR_REALTIME,
  TIER_2_DAILY, TIER_3_BACKUP_RESTORE
- **DR_PLAN_STATES** (4) Rule 4: DRAFT, ACTIVE, DEPRECATED, ARCHIVED
- **DRILL_TYPES** (4): TABLETOP, WALKTHROUGH, SIMULATION, FULL_FAILOVER
- **DRILL_STATES** (5) Rule 4: SCHEDULED, IN_PROGRESS, COMPLETED,
  FAILED, CANCELLED
- DEFAULT_RTO_TARGET_HOURS = **4** (CBK target)
- DEFAULT_RPO_TARGET_MINUTES = **15** (CBK target)
- CBK_DR_REGULATORY_REFERENCE = **"CBK Cybersecurity Guidance"** (Cat B)

- **API_VERSION_STATES** (5) Rule 4: DEVELOPMENT, BETA, GA, DEPRECATED,
  RETIRED
- **RATE_LIMIT_WINDOWS** (4): SECOND, MINUTE, HOUR, DAY
- **AUTH_SCHEMES** (4): OAUTH2_BEARER, OPENID_CONNECT, API_KEY, MUTUAL_TLS
- **API_KEY_STATES** (4): ACTIVE, REVOKED, EXPIRED, PENDING
- DEFAULT_RATE_LIMIT_PER_MINUTE = **60**
- DEFAULT_RATE_LIMIT_BURST_FACTOR = **2**

---

## Behavioural rules locked

- **ITSM**: incident priority must be P1-P4; state machine prevents
  illegal transitions; re-open path enforced (RESOLVED → IN_PROGRESS);
  change rollback always reachable from IMPLEMENTED or FAILED.
- **Cloud**: 12-factor compliance dict validated against canonical 12
  criteria; portability score = compliance% with bonuses for
  multi-provider readiness; A-F grading; deployment ROLLED_BACK can
  re-deploy to DEPLOYED after fix.
- **Observability**: SLO target_pct must be 0 < x ≤ 100; error budget
  consumed % capped at 100; burn alert at ≥50%; budget policy choices
  enforced from canonical 3.
- **DR/BCP**: RTO/RPO targets must be positive Decimals; CBK compliance
  flag requires target ≤ CBK threshold AND zero historical breaches;
  drill type and state transitions locked; runbook steps must be
  non-empty list.
- **API Gateway**: rate limit count uses time-bucketed call counting;
  `within_burst` separate from `within_limit` (burst = limit ×
  burst_factor); fallback to DEFAULT_RATE_LIMIT_PER_MINUTE = 60 when
  no policy attached; usage summary segregates 2xx/4xx/5xx.

---

## G162 baseline rebase (9th in Phase 2A)

| Token    | Before | After  | Delta | Note                                                                                                                                                                                                                                                                       |
|----------|--------|--------|-------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| FLEXCUBE | 204    | 210    | +6    | Core-banking-system references: it_itsm test fixture INC-001 'FLEXCUBE login failure', it_disaster_recovery test SVC-FLEXCUBE binding + RB-001 'FLEXCUBE Failover' runbook + Standard() metadata + G174 audit + Tier 43 admin                                              |
| CBK      | 1296   | 1318   | +22   | Kenyan-regulator references: it_disaster_recovery `CBK_DR_REGULATORY_REFERENCE` constant + `regulatory_reference` field on every DR plan + ENH-294 Cat B regulatory_source + G174 audit gate references + Tier 43 admin description + page 96 DR tab caption                |
| **Total**| 3818   | 3846   | **+28** | Ninth consecutive Phase 2A rebase                                                                                                                                                                                                                                          |

All increases are byte-for-byte regulatory citation or jurisdiction-bound
test fixture references. Renaming would either break G174 byte-for-byte
lock (`CBK_DR_REGULATORY_REFERENCE` is a constant explicitly locked in
the audit gate) or remove regulator-meaningful semantics (CBK
Cybersecurity Guidance is the canonical reference for Kenyan banks'
DR/BCP framework).

ENH-294 is the cluster's sole Category B (regulatory) standard — its
CBK binding is non-negotiable. Same precedent as v10.271 (+28 CBK SLA
citations).

Cumulative Phase 2A scope_history: v10.271 +28, v10.273 +13, v10.274 +20,
v10.276 +9, v10.277 +29, v10.278 +4, v10.279 +29, v10.280 +15, **v10.281 +28** =
+175 tokens across 9 cluster closures, with full deterministic accounting.

---

## Files changed

```
utils/it_itsm.py                                NEW (458 lines)
utils/it_cloud_architecture.py                  NEW (388 lines)
utils/it_observability.py                       NEW (442 lines)
utils/it_disaster_recovery.py                   NEW (491 lines, Cat B)
utils/it_api_gateway.py                         NEW (459 lines)
pages/96_it_digital_pt1.py                      NEW (7 tabs, audit_log wired)
utils/standards_registry.py                     ENH-291..295 flipped status="active", batch="v10.281"
scripts/audit.py                                G174 gate_it_digital_pt1_registered registered (locks 5 modules + 19 enum tuples + 4 ALLOWED dicts + 6 spec constants byte-for-byte)
pages/7_admin.py                                Tier 43 added with all 5 engine entries
pages/_manifest.json                            96_it_digital_pt1.py registered with department_primary="shared"
data/audit_baselines.json                       G162 rebased 3818 → 3846 (+28) with full v10.281 scope_history entry
CHANGELOG_v10.281.md                            NEW (this document)
```

---

## Audit summary

```
  Score: 174/174 gates = 100.0% — PASS
```

All gates green. Phase 2A 9/16 cluster closures.

---

## Next batches (sequential queue)

- **v10.282** — IT/Digital Foundation pt 2 (#296–#300) — 5 standards, page 97, G175, Tier 44
- **v10.283** — SWIFT (#272 — Trade Finance lone) — page 98, G176, Tier 45
- **v10.284** — QA Map document for Ecobank presentation
- **v10.285** — Phase 2A retrospective + master prompt update + memory rebaseline
