# A2Z Blueprint MIS 360 — Data Dictionary

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md`)
**Status:** `canonical_with_unknown_subareas`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 4)
**Last updated:** 2026-05-22
**Owner:** Architecture / Doctrine + per-domain owners
**Authoritative source:** `data/` directory (file system) + `data/_schemas/` (where present)
**Machine-readable equivalent:** `DATA_DICTIONARY.json`

---

## Purpose

This document catalogs every persistent data file in the A2Z system. For each file it declares:

- **Owner** — which organ writes / which team is accountable
- **Authority** — `canonical` / `derived` / `transitional` / `deprecated`
- **Schema status** — whether `data/_schemas/*.json` declares its shape
- **Consumers** — which modules read it
- **Retention** — backup policy, gitignore status, lifecycle

Per Article VI of `SYSTEM_CONSTITUTION.md`: every file in `data/` has a declared owner; where schemas exist they are canonical for shape; backups follow the `data/_v10XXX_backups/` retention pattern and are gitignored.

---

## Doctrine

**DD1 — Every file has an owner.** No `data/*.json` exists without an organ that owns writes to it. Anonymous data files are violations.

**DD2 — Where schema exists, it is canonical.** If `data/_schemas/<file>.json` declares the shape of `data/<file>.json`, the schema wins. Consumers must validate.

**DD3 — Backup directories are gitignored.** Pattern: `data/_v10XXX_backups/`. Retention enforced by `/api/v1/backup-retention/audit` + `apply`.

**DD4 — Append-only data has different rules than mutable data.** Audit logs and event streams are append-only (never edit historical entries). Configuration files and registries are mutable but every change is audited.

**DD5 — Personal Identifying Information must not be checked into git.** `users.json` is in git (intentional — seed data with synthetic identities); `audit_log.json` is gitignored; `cookies.txt` is gitignored.

---

## File inventory

### Authentication & user identity

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/users.json` | `UserManager` | canonical | TBD | All auth flows, hierarchy synth, BSC, cascade, all role-aware engines | git-tracked; backups by batch |
| `data/jwt_blocklist.json` | `utils/auth_jwt.py::revoke_token` | canonical | inline (jti → exp epoch) | `_is_revoked` | git-tracked; auto-prunes expired entries |
| `data/pending_tokens.json` | TBD (likely auth flow) | unknown | none | TBD | TBD — surveyed in Stage A inventory but content unknown |
| `data/super_user_registry.json` | `utils/super_user_registry.py` | canonical | TBD | Admin operations | git-tracked |

**OI-25** — `pending_tokens.json` purpose and lifecycle to be confirmed in Stage C.

### Org hierarchy & role taxonomy

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/org_hierarchy_config.json` | Admin / HR Operations | canonical | inline `_schema_version: v10.330` | `utils/role_taxonomy.py`, `utils/hierarchy_synth.py`, `utils/profitability_hierarchy.py`, `utils/cascade_hierarchy.py`, all RBAC | git-tracked |
| `data/segment_sbu_mapping.json` | Admin / Business | canonical | TBD | `role_taxonomy.py` (SBU alignment check per G260) | git-tracked |
| `data/org_config.json` | Admin / Tenant Onboarding | canonical | TBD | `utils/config.py`, `/api/branding`, all transports | git-tracked |
| `data/hr.json` | `HRManager` | canonical | TBD | `role_taxonomy.validate_role_coverage`, hierarchy synth, HR engines | git-tracked |
| `data/staff_register.xlsx` | `HRManager` | canonical | column conventions documented in `HRManager` | Generators (`generate_staff.py`), `staff_*_resolver.py` | git-tracked |
| `data/hr_disciplinary.json` | `HRManager` | canonical | TBD | HR section audit | git-tracked |
| `data/hr_exits.json` | `staff_exit_engine` | canonical | TBD | HR analytics | git-tracked |
| `data/hr_pip.json` | `HRManager` | canonical | TBD | Performance improvement plans | git-tracked |
| `data/hr_transfers.json` | `HRManager` | canonical | TBD | Transfer history | git-tracked |
| `data/disciplinary_register.json` | `HRManager` | canonical | TBD | Disciplinary audit | git-tracked |
| `data/leave_*.json` | `LeaveManager` | canonical | TBD | Leave administration | git-tracked |
| `data/performance_reviews.json` | `HRManager` + performance engines | canonical | TBD | Performance dashboards | git-tracked |
| `data/role_skill_matrix.json` | Admin / Performance | canonical | inline default + per-role overrides | Skill-gap analysis, peer learning | git-tracked (3.6 KB) |
| `data/role_default_targets.json` | Admin / Performance | canonical | inline `_meta` block | BSC target fallback | git-tracked (5.4 KB) |

### KPI library & BSC core

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/kpi_library.json` | Performance / BSC governance | canonical | TBD; harmonization batches stamped in file | All BSC engines, cascade, actuals, role_kpis resolver | git-tracked |
| `data/bsc_data.json` | `canonical_bsc_writer` | canonical | inline | BSC dashboards, cascade reconciliation | git-tracked |
| `data/bsc_scores.json` | `bsc_score_computation` | derived | (computed from bsc_data + targets) | BSC dashboards | git-tracked |
| `data/bsc_actuals_*.json` (8 periods) | actuals engines + canonical_bsc_writer | canonical (per period) | TBD | Period reports, BSC audit | git-tracked |
| `data/bsc_lock.json` | Admin via `lock_bsc`/`unlock_bsc` (utils/core.py) | canonical | inline | BSC engine lock check | git-tracked |
| `data/fixed_kpis.json` | Admin | canonical | TBD | BSC target fallback (top of precedence chain) | git-tracked |
| `data/kpi_ownership_map.json` | KPI governance | canonical | TBD | Routing rules for KPI changes | git-tracked |
| `data/pillar_weights_history.json` | `pillar_weights_canonical` | append-only canonical | TBD | Audit of weight changes over time | git-tracked |

### Target cascade

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/bank_targets.json` | Admin (top-down targets) | canonical | TBD | MD BSC, cascade root | git-tracked |
| `data/target_cascade.json` | `CascadeManager` + cascade engines | canonical | TBD | Per-staff target resolution | git-tracked |
| `data/locked_targets.json` | Cascade lock mechanism | canonical | TBD | Prevent re-cascade during period | git-tracked |
| `data/buffer_caps.json` | `cascade_buffer_engine` | canonical | TBD | Buffer cap enforcement | git-tracked |
| `data/cascade_scores_*.json` (4 periods) | Cascade engines | derived | (computed from cascade + actuals) | Cascade audit endpoints | git-tracked |

### CBS / Virtual bank (banking simulation)

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/cbs_baseline_*.json` | `cbs_baseline.py` + generators | canonical | TBD | Live actuals overlay | git-tracked |
| `data/baseline_2025_Dec.json` | Generator script | canonical | TBD | Year-end snapshot | git-tracked |
| `data/branch_actuals.json` | `vb_actuals_bridge` | canonical | TBD | Branch performance | git-tracked |
| `data/accruals_assumptions.json` | `accruals_synthesizer` | canonical | TBD | Accruals computation | git-tracked |
| `cbs_data/` (separate dir at project root) | `generate_cbs.py` | canonical | TBD | CBS exploration page | likely gitignored (large) |

### Pipeline / CRM

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/pipeline.json` | `PipelineManager` | canonical | TBD | Pipeline summary/deals endpoints | git-tracked |
| `data/deal_rooms.json` | `PipelineManager` | canonical | TBD | Deal room views | git-tracked |
| `data/ri_pipeline.json` | `RIPipelineManager` | canonical | TBD | RI pipeline views | git-tracked |

### Credit

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/credit_admin.json` | `CreditAdminManager` | canonical | TBD | Credit admin | git-tracked |
| `data/credit_monitoring.json` | `CreditAdminManager` | canonical | TBD | Credit monitoring | git-tracked |
| `data/loan_applications.json` | `LoanApplicationManager` | canonical | TBD | Loan workflow | git-tracked |
| `data/loan_restructuring.json` | TBD | canonical | TBD | Restructuring tracking | git-tracked |
| `data/ews_cases.json` | `CreditAdminManager` (EWS = Early Warning Signals) | canonical | TBD | EWS dashboards | git-tracked |
| `data/collateral.json` | TBD | canonical | TBD | Collateral tracking | git-tracked |
| `data/collateral_register.json` | TBD | canonical | TBD | Collateral register | git-tracked |

### Risk & compliance

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/aml_alerts.json` | `aml_monitoring` | canonical | TBD | AML dashboards | git-tracked |
| `data/compliance_cases.json` | `ComplianceManager` | canonical | TBD | Compliance dashboard | git-tracked |
| `data/sanctions_register.json` | `sanctions_screening` | canonical | TBD | Screening checks | git-tracked |
| `data/op_risk_losses.json` | `op_risk` | canonical | TBD | Op risk reporting | git-tracked |
| `data/ifrs9_*.json` | `ifrs9_classification` | canonical | TBD | IFRS 9 reporting | git-tracked |
| `data/rcsa_register.json` | Risk & Compliance | canonical | TBD | RCSA tracking | git-tracked |

### Treasury

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/treasury_alm.json` | `treasury_alm` | canonical | TBD | ALM dashboards | git-tracked |
| `data/treasury_fd.json` | TBD | canonical | TBD | Fixed deposits | git-tracked |
| `data/treasury_fx.json` | `fx_position` | canonical | TBD | FX positions | git-tracked |
| `data/treasury_gov_secs.json` | TBD | canonical | TBD | Government securities | git-tracked |
| `data/treasury_limits.json` | `market_risk_limits` + `climate_treasury_limits` | canonical | TBD | Limit monitoring | git-tracked |
| `data/treasury_mm.json` | TBD | canonical | TBD | Money market | git-tracked |
| `data/liquidity_metrics.json` | `liquidity_risk` | canonical | TBD | Liquidity dashboards | git-tracked |

### Execute / strategic initiatives

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/strategic_initiatives.json` | `ExecuteManager` | canonical | TBD | Initiative dashboard | git-tracked |
| `data/execute_*.json` | `ExecuteManager` | canonical | TBD | Execute workflow | git-tracked |
| `data/strategy_*.json` | strategy modules | canonical | TBD | Strategy dashboards | git-tracked |

### CIMS (Customer Info Management System)

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/cims*.json` (multiple) | CIMS engines (15 modules) | canonical | TBD | CIMS workflow | git-tracked |
| `data/cims_docs/` (subdir) | CIMS document store | canonical | TBD | Secure document storage | TBD |

### Audit & telemetry (append-only)

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/audit_log.json` | `utils/api.py::_audit` | canonical | TBD | Audit dashboards, compliance | **gitignored** (runtime telemetry) |
| `data/audit_trail.jsonl` | Various | canonical | JSONL | Audit dashboards | **gitignored** |
| `data/audit_baselines.json` | Audit engines | canonical | TBD | Drift detection | git-tracked |
| `data/audit_reviews.json` | Audit reviewers | canonical | TBD | Audit history | git-tracked |
| `data/observability_metrics.json` | `observability_monitoring` | canonical | TBD | Metrics dashboards | TBD (likely gitignored) |
| `audit_trail_certification` outputs | `utils/audit_trail_certification` | canonical | TBD | Certification ledger | TBD |

### Validation & schema

| File | Owner | Authority | Schema | Consumers | Retention |
|---|---|---|---|---|---|
| `data/validations.json` | `ValidationManager` | canonical | TBD | Validation runs | git-tracked |
| `data/_schemas/` (directory) | Schema authors per domain | canonical | self-describing JSON Schema | Validators | git-tracked |

**OI-26** — Contents of `data/_schemas/` not yet surveyed. Wave 4 amendment will enumerate.

### Backups (gitignored)

| Pattern | Owner | Authority | Purpose | Retention |
|---|---|---|---|---|
| `data/_v10XXX_backups/` | Admin (backup engine) | derived | Pre-batch snapshots | enforced by `/api/v1/backup-retention/audit` + `apply` |

Retention policy parameters:
- `keep_recent: int = 3` — keep last 3 backups
- `size_threshold_mb: float = 1.0` — delete backups under threshold older than retention

### Generated / runtime artifacts (gitignored)

| File | Owner | Authority | Purpose |
|---|---|---|---|
| `cookies.txt` | curl test artifacts | derived | Local testing only |
| `*_response.json` | curl test artifacts | derived | Local testing only |
| `data/audit_log.json` | (already listed) | canonical (runtime) | gitignored |
| `data/audit_trail.jsonl` | (already listed) | canonical (runtime) | gitignored |
| `cbs_data/*` (likely) | `generate_cbs.py` output | derived | Large simulated dataset |

---

## File count summary

From Stage A survey context: **~250 distinct JSON files** in `data/` + **2 XLSX workbooks** (`actuals_2025_Dec_25.xlsx`, `staff_register.xlsx`) + multiple `_v10XXX_backups/` directories (gitignored).

This Wave 4 catalog explicitly documents **~65 files**. The remaining ~185 files are domain-specific (CIMS sub-files, compliance sub-files, segment data, scenario libraries) and will be enumerated in Wave 5 (`DIGITAL_TWIN_ARCHITECTURE`, `AI_GOVERNANCE`, `RESILIENCE_AND_CERTIFICATION_GOVERNANCE`).

---

## Schema governance

### Where schemas exist

`data/_schemas/` contains JSON Schema files for some `data/*.json` files. Where a schema exists:

- It is the canonical declaration of shape
- Consumers must validate (currently best-effort; Stage C will enforce)
- Updates to the data file must conform to the schema, OR the schema must be updated in the same commit

### Where schemas don't exist

For files without an explicit schema, the **consuming module's parsing code is the de facto contract**. This is `transitional` — Stage C will require schemas for all `canonical` data files.

### Schema introduction policy (Stage C)

When introducing a schema for an existing file:

1. Author the schema in `data/_schemas/<file>.json`
2. Run validation against all production data; fix mismatches
3. Add an audit gate `gate_<file>_schema_compliance` with initial severity `LOW` (visibility phase)
4. After 1 batch grace, escalate to `MEDIUM`
5. After 2 more batches, escalate to `HIGH`
6. After remediation complete, escalate to `CRITICAL`

This is the **Phase 1 Visibility → Phase 2 Grace → Phase 3 Full Enforcement** rollout from `GOVERNANCE_CLASSIFICATION_REGISTRY.md`.

---

## PII and sensitive data

Per DD5: PII must not be in git unless intentional and synthetic.

### Intentional in git (synthetic seed data)

- `data/users.json` — 1,439 users with synthetic identities (Ecobank-style names) used for the demo/simulation. Real production deployment requires replacement with tenant data via Admin import.
- `data/hr.json` — synthetic HR records (synthetic).
- `data/staff_register.xlsx` — synthetic staff register.

### Forbidden in git (runtime / sensitive)

- `data/audit_log.json` — may contain user actions; gitignored
- `data/audit_trail.jsonl` — same
- `cookies.txt`, `*_response.json` — local test artifacts
- Any future PostgreSQL credentials, API keys, secrets — must go through environment variables, never files

### Multi-tenant isolation

`utils/data_isolation_guard.py` is the canonical helper for multi-tenant boundaries (purpose surveyed; full contract TBD). When the system serves multiple tenants, every read must declare tenant scope, and `data_isolation_guard` enforces.

**OI-27** — Survey `utils/data_isolation_guard.py` contract in Stage C.

---

## Lifecycle states for data files

| State | Meaning | Examples |
|---|---|---|
| `canonical` | Source of truth; writes go here | `org_hierarchy_config.json`, `users.json`, `kpi_library.json` |
| `derived` | Computed from other canonical sources | `bsc_scores.json`, `cascade_scores_*.json` |
| `append_only_canonical` | Canonical but never edits historical | `audit_log.json`, `pillar_weights_history.json`, `audit_trail.jsonl` |
| `transitional` | Currently in use, being migrated | `users.json::password` field (SHA-256 → bcrypt) |
| `deprecated` | Existed, replaced, retained for legacy | (none currently identified) |
| `unknown` | Discovered, not yet classified | `pending_tokens.json` (OI-25), `data/_schemas/` contents (OI-26) |

---

## PostgreSQL migration tracking

Per audit gates `gate_pg_migration_progress`, `gate_pg_migration_baseline`, `gate_pg_read_path_cutover`, `gate_pg_ready_composer_fanout`, `gate_pg_production_cutover`, `gate_pg_cutover_fanout`: the system is migrating from JSON file storage to PostgreSQL.

Current state (per session memory): JSON files remain canonical for most domains; PostgreSQL is the eventual target. Migration is **transitional**.

Files in scope for migration (high priority):
- `data/users.json` — high read volume, lookup-heavy
- `data/bsc_data.json` + `bsc_actuals_*` — large per-period datasets
- `data/audit_log.json` → likely event sourcing in PG instead of JSON append

Files likely to remain JSON (low write volume, config-like):
- `data/org_hierarchy_config.json`
- `data/kpi_library.json`
- `data/org_config.json`
- `data/role_default_targets.json`, `data/role_skill_matrix.json`

**OI-28** — PostgreSQL migration roadmap will be documented in `REVIVAL_LEDGER.md` (Wave 6) with per-file migration status.

---

## Open items

| ID | Title | Resolution wave |
|---|---|---|
| OI-25 | `pending_tokens.json` purpose and lifecycle | Stage C |
| OI-26 | Enumerate `data/_schemas/` contents | Wave 4 amendment |
| OI-27 | Survey `utils/data_isolation_guard.py` contract | Stage C |
| OI-28 | PostgreSQL migration roadmap per file | Wave 6 REVIVAL_LEDGER |
| OI-29 | Schema introduction rollout for all canonical files without schema | Stage C (per Phase 1/2/3 rollout) |
| OI-30 | Catalog remaining ~185 domain-specific data files (CIMS, scenarios, segment-specific) | Wave 5 |

---

**End of DATA_DICTIONARY.md**
