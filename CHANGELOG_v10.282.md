# Changelog — v10.282 IT/Digital Foundation pt 2

**Date:** 2026-05-08
**Phase:** 2A — Active-standards expansion
**Cluster:** IT/Digital Foundation pt 2 (Standards #296–#300)
**Audit:** 175/175 gates PASS = 100.0%
**G162 Rebase:** 3846 → 3901 (+55)

---

## Summary

Phase 2A v10.282 ships the **IT/Digital Foundation pt 2 cluster** —
5 engines covering 5 standards (#296–#300). Audience: CISO, CTO,
CIO, security engineering, compliance, audit.

This batch completes the IT/Digital arc: data encryption + secrets
vault + PII registry under DPA Kenya 2019 and CBK Cybersecurity,
CI/CD pipelines with DORA-style metrics, multi-tenancy with white
labelling and feature flags, the digital banking suite (mobile +
web sessions, push notifications, biometric enrolment), and
formal CBK IT compliance and certification tracking against four
frameworks (CBK Cybersecurity, ISO 27001, PCI DSS, SOC 2 Type II).

This is the **19th closed cluster** in Phase 2A and the **79th
consecutive clean batch** since v10.193. ENH-296 and ENH-300 are
the cluster's two Category B (regulatory) standards — their DPA
Kenya 2019 and CBK Cybersecurity Guidance bindings are locked
under G175 byte-for-byte.

---

## Standards delivered

| Standard | Title                                                       | Engine                  | Cat |
|----------|-------------------------------------------------------------|-------------------------|-----|
| ENH-296  | Data Encryption & Security Hardening                        | it_data_encryption      | B   |
| ENH-297  | CI/CD & Release Automation                                  | it_cicd                 | C   |
| ENH-298  | Multi-Tenancy & White Labeling                              | it_multi_tenancy        | C   |
| ENH-299  | Digital Banking Suite (Mobile + Web)                        | it_digital_banking      | C   |
| ENH-300  | CBK IT Compliance & Certification                           | it_cbk_compliance       | B   |

5 standards across 5 engines. 2 Category B regulatory (#296, #300).

---

## Engines shipped

| #   | Module                           | Standard | Lines |
|-----|----------------------------------|----------|-------|
| 1   | `utils/it_data_encryption.py`    | #296     | 425   |
| 2   | `utils/it_cicd.py`               | #297     | 384   |
| 3   | `utils/it_multi_tenancy.py`      | #298     | 442   |
| 4   | `utils/it_digital_banking.py`    | #299     | 488   |
| 5   | `utils/it_cbk_compliance.py`     | #300     | 481   |

**Page:** `pages/97_it_digital_pt2.py` — 7 tabs, audit_log on every
write surface (G3 compliant), G4 compliant. Tab 7 (Compliance &
Certifications) uses 6 sub-tabs with state-transition forms folded
into expanders inside their primary register tabs to stay under the
hard limit.

---

## Specification invariants locked under G175

### Encryption (#296, Cat B)
- **ENCRYPTION_ALGORITHMS** (4): AES_256_GCM, AES_256_CBC, RSA_4096, ECDSA_P384
- **KEY_STATES** (5) Rule 4: PENDING, ACTIVE, ROTATING, DEPRECATED, DESTROYED
- **KEY_USAGE_PURPOSES** (5): DATA_AT_REST, DATA_IN_TRANSIT, FIELD_LEVEL, SIGNING, AUTHENTICATION
- **SECRET_TYPES** (6): DATABASE_PASSWORD, API_KEY, SERVICE_ACCOUNT, TLS_CERTIFICATE, ENCRYPTION_KEY, OAUTH_CLIENT_SECRET
- **SECURITY_EVENT_TYPES** (7): KEY_ROTATION, SECRET_ROTATION, ACCESS_GRANT, ACCESS_REVOKE, POLICY_VIOLATION, SUSPICIOUS_ACCESS, AUDIT_FAILURE
- **PII_SENSITIVITY_LEVELS** (4): LOW, MEDIUM, HIGH, CRITICAL
- DEFAULT_KEY_ROTATION_DAYS = **90** (CBK Cybersecurity recommended)
- DEFAULT_SECRET_ROTATION_DAYS = **60**
- DPA_KENYA_REGULATORY_REFERENCE = **"Data Protection Act 2019"**

### CI/CD (#297)
- **PIPELINE_TYPES** (4): GITHUB_ACTIONS, GITLAB_CI, JENKINS, ARGOCD
- **PIPELINE_STAGES** (6): BUILD, TEST, SECURITY_SCAN, STAGING_DEPLOY, PROD_DEPLOY, ROLLBACK
- **PIPELINE_STATES** (3) Rule 4: ACTIVE, PAUSED, ARCHIVED
- **RUN_STATES** (6) Rule 4: QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED, TIMED_OUT
- **ENVIRONMENT_TYPES** (5): DEV, TEST, STAGING, UAT, PRODUCTION
- DEFAULT_BUILD_TIMEOUT_MINUTES = **30**
- DEFAULT_DEPLOY_TIMEOUT_MINUTES = **15**

### Multi-Tenancy (#298)
- **TENANT_STATES** (5) Rule 4: PROVISIONING, ACTIVE, SUSPENDED, OFFBOARDING, ARCHIVED
- **ISOLATION_MODELS** (3): DEDICATED_DATABASE, SHARED_DB_DEDICATED_SCHEMA, SHARED_DB_SHARED_SCHEMA
- **BRANDING_ELEMENTS** (6): LOGO_URL, PRIMARY_COLOR, SECONDARY_COLOR, FAVICON_URL, EMAIL_SENDER, SUPPORT_PHONE
- **FLAG_TYPES** (3): BOOLEAN, PERCENTAGE_ROLLOUT, ALLOWLIST
- **FEATURE_FLAG_STATES** (3) Rule 4: ACTIVE, DEPRECATED, ARCHIVED

### Digital Banking (#299)
- **APP_PLATFORMS** (4): IOS, ANDROID, WEB, RESPONSIVE_WEB
- **APP_VERSION_STATES** (5) Rule 4: ALPHA, BETA, RELEASED, DEPRECATED, DISCONTINUED
- **SESSION_STATES** (5) Rule 4: ACTIVE, IDLE, EXPIRED, REVOKED, SIGNED_OUT
- **NOTIFICATION_TYPES** (5): TRANSACTIONAL, ALERT, MARKETING, SECURITY, SYSTEM
- **NOTIFICATION_STATES** (4): PENDING, SENT, DELIVERED, FAILED
- **BIOMETRIC_TYPES** (4): FINGERPRINT, FACE_ID, IRIS, VOICE
- DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES = **5**
- DEFAULT_SESSION_HARD_TIMEOUT_MINUTES = **30**

### CBK Compliance (#300, Cat B)
- **COMPLIANCE_FRAMEWORKS** (4): CBK_CYBERSECURITY, ISO_27001, PCI_DSS, SOC_2_TYPE_II
- **PROGRAM_STATES** (4) Rule 4: PLANNED, IN_PROGRESS, ACTIVE, RETIRED
- **CONTROL_CATEGORIES** (6): ACCESS_CONTROL, CRYPTOGRAPHY, INCIDENT_RESPONSE, BUSINESS_CONTINUITY, VENDOR_MANAGEMENT, AUDIT_LOGGING
- **FINDING_SEVERITIES** (4): LOW, MEDIUM, HIGH, CRITICAL
- **FINDING_STATES** (5) Rule 4: OPEN, REMEDIATION_IN_PROGRESS, RESOLVED, ACCEPTED_RISK, OVERDUE
- **CERTIFICATION_STATES** (5) Rule 4: PENDING, ACTIVE, EXPIRING_SOON, EXPIRED, REVOKED
- CBK_REGULATORY_REFERENCE = **"CBK Cybersecurity Guidance"**
- DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY = **{CRITICAL: 7, HIGH: 30, MEDIUM: 60, LOW: 90}**

---

## Behavioural rules locked

- **Encryption**: invalid algorithm or purpose rejected; KEY_STATES enforce DESTROYED terminal; HSM coverage and critical-PII coverage reported separately; secrets auto-set next_rotation_at on register and bump rotation_count on rotate; PII fields with HIGH/CRITICAL sensitivity force `encryption_required=True` automatically.
- **CI/CD**: pipeline stages must come from canonical 6; run state machine enforces all four terminal states (SUCCEEDED, FAILED, CANCELLED, TIMED_OUT); duration_seconds auto-computed when run reaches a terminal from RUNNING; `pipeline_metrics` returns success rate + average duration over rolling window; `deployment_frequency` returns deploys-per-day.
- **Multi-Tenancy**: branding elements must come from canonical 6; tenant ARCHIVED is terminal but ACTIVE↔SUSPENDED roundtrip allowed; `tenant_isolation_check` enforces per-model invariants (DEDICATED_DATABASE requires `database_url_ref`, SHARED_DB_DEDICATED_SCHEMA requires `schema_name`); `set_tenant_feature` is upsert and rejects archived flags.
- **Digital Banking**: session ACTIVE↔IDLE allowed but IDLE→ACTIVE bumps `last_active_at`; `session_continuity_check` flags `omnichannel=True` only when ≥2 distinct platforms have sessions for the same customer; biometric type must be one of canonical 4; notification metrics segregate delivered vs failed and compute delivery rate %.
- **CBK Compliance**: program ACTIVE↔IN_PROGRESS allowed (re-baseline); finding records auto-compute `sla_due_at` from severity (CRITICAL=7d down to LOW=90d); cert state machine permits EXPIRED→ACTIVE re-issue but REVOKED is terminal; `compliance_summary` accepts framework filter and reports `regulatory_reference` per framework.

---

## G162 baseline rebase (10th in Phase 2A)

| Token   | Before | After  | Delta  | Note                                                                                                                                                                                                                                                                                                                                                          |
|---------|--------|--------|--------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| CBK     | 1318   | 1368   | +50    | `CBK_REGULATORY_REFERENCE` constant + `CBK_CYBERSECURITY` framework enum value used across G175 audit gate locks + Tier 44 admin description + page 97 framework selectboxes + ENH-300 Standard() name "CBK IT Compliance" + ENH-296 regulatory_source "DPA Kenya + CBK Cyber" + compliance_summary regulatory_reference branch                                |
| Kenya   | 288    | 292    | +4     | `DPA_KENYA_REGULATORY_REFERENCE = "Data Protection Act 2019"` constant in encryption module + Standard() regulatory_source for ENH-296 + Tier 44 description + page 97 PII tab caption                                                                                                                                                                        |
| Ecobank | 111    | 112    | +1     | Multi-tenancy self-test fixture `TENANT-EBK` with `tenant_name="Ecobank Kenya"` (scenario-realistic primary client tenant)                                                                                                                                                                                                                                    |
| **Total** | 3846 | 3901   | **+55** | Tenth consecutive Phase 2A rebase                                                                                                                                                                                                                                                                                                                            |

All increases are byte-for-byte regulatory citation or jurisdiction-bound
test fixture references. Renaming would either break G175 byte-for-byte
lock (`CBK_REGULATORY_REFERENCE` and `DPA_KENYA_REGULATORY_REFERENCE`
are constants explicitly locked in the audit gate; `CBK_CYBERSECURITY`
is a `COMPLIANCE_FRAMEWORKS` enum value used across the codebase) or
remove regulator-meaningful semantics (CBK Cybersecurity Guidance is
the canonical reference for Kenyan banks' cybersecurity framework;
Data Protection Act 2019 is the canonical Kenyan PII regulation).

ENH-296 and ENH-300 are the cluster's two Category B regulatory
standards — their CBK and DPA Kenya bindings are non-negotiable.
Same precedent as v10.281 (+28 CBK references for DR/BCP).

Cumulative Phase 2A scope_history: v10.271 +28, v10.273 +13,
v10.274 +20, v10.276 +9, v10.277 +29, v10.278 +4, v10.279 +29,
v10.280 +15, v10.281 +28, **v10.282 +55** = +230 tokens across 10
cluster closures, with full deterministic accounting.

---

## Files changed

```
utils/it_data_encryption.py                NEW (425 lines, Cat B)
utils/it_cicd.py                           NEW (384 lines)
utils/it_multi_tenancy.py                  NEW (442 lines)
utils/it_digital_banking.py                NEW (488 lines)
utils/it_cbk_compliance.py                 NEW (481 lines, Cat B)
pages/97_it_digital_pt2.py                 NEW (7 tabs, audit_log wired)
utils/standards_registry.py                ENH-296..300 flipped status="active", batch="v10.282"
scripts/audit.py                           G175 gate_it_digital_pt2_registered registered (locks 5 modules + 26 enum tuples + 6 ALLOWED dicts + 9 spec constants byte-for-byte)
pages/7_admin.py                           Tier 44 added with all 5 engine entries
pages/_manifest.json                       97_it_digital_pt2.py registered with department_primary="it_platform"
data/audit_baselines.json                  G162 rebased 3846 → 3901 (+55) with full v10.282 scope_history entry
CHANGELOG_v10.282.md                       NEW (this document)
```

---

## Audit summary

```
  Score: 175/175 gates = 100.0% — PASS
```

All gates green. Phase 2A 10/16 cluster closures.

---

## Next batches (sequential queue)

- **v10.283** — SWIFT (#272 — Trade Finance lone) — page 98, G176, Tier 45
- **v10.284** — QA Map document for Ecobank presentation
- **v10.285** — Phase 2A retrospective + master prompt update + memory rebaseline + UI integration backfill plan
