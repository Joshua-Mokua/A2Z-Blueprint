# A2Z Blueprint MIS 360 — Canonical Truth Registry

**Type:** Constitutional artifact, governance layer
**Authority level:** Constitution (this artifact defines authority itself)
**Status:** `canonical`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 1)
**Last updated:** 2026-05-22
**Owner:** A2Z constitution maintainers
**Machine-readable equivalent:** `CANONICAL_TRUTH_REGISTRY.json`

---

## Purpose

This is the **top-level resolver** for the entire A2Z architecture. For every architectural domain — roles, KPIs, auth, telemetry, etc. — this registry declares:

1. **The authoritative source-of-truth** (the file, table, or module that *defines* truth for that domain)
2. **Derived artifacts** that consume from the authoritative source
3. **The conflict-resolution rule** when sources disagree
4. **The enforcement mechanism** that prevents drift
5. **The owner** accountable for the canonical state

When any tool, AI session, audit gate, or human collaborator needs to know "what does the system consider canonical for X?", the answer starts here.

This artifact **does not contain the canonical data itself.** It contains pointers. The data lives in the files it points to. Updating canonical data means updating the pointed-to file; updating this registry means changing the pointer or the authority rules.

---

## Doctrine

**D1 — One source of truth per domain.** Multiple files may *consume* canonical data, but exactly one file *defines* it. Where consumers diverge from the source, the source wins; the consumers are reconciled (not the source).

**D2 — Drift is detected by gates, not by audit prose.** Every entry in this registry must have an audit gate that mechanically verifies the source-of-truth is internally consistent and that declared consumers agree with it.

**D3 — Authority can change; lineage must not be lost.** When a source-of-truth migrates (e.g. JSON → PostgreSQL), the old location stays referenced in this registry as `superseded_by` with a date and rationale. The migration is recorded in `REVIVAL_LEDGER.md`.

**D4 — Sources point to data; pointers don't drift silently.** Every pointer in this registry is a file path. Changes to those pointers (renames, moves) must update this registry in the same commit. Audit gate `gate_canonical_truth_registry_sync` enforces this.

**D5 — Conflicts have an explicit winner.** When two files might disagree (e.g. a user's role in `users.json` vs a manual override elsewhere), this registry declares which wins.

---

## How to read this registry

Each domain section has:

- **Authoritative source** — the canonical file/table
- **Consumers** — files that read but don't define
- **Conflict rule** — what happens when source ≠ consumer
- **Enforcement** — audit gate that verifies
- **Owner** — accountable for keeping canonical
- **Classification** — `canonical`, `derived`, `transitional`, `deprecated`, `unknown` (per `GOVERNANCE_CLASSIFICATION_REGISTRY.md`)

When a consumer wants to make a logic decision, it must call into the authoritative source's interface, not parse the file independently. Direct file reads from outside `utils/<canonical_module>.py` are a violation unless explicitly listed below.

---

## Registry

### Domain: Tenant identity & branding

| Field | Value |
|---|---|
| Authoritative source | `data/org_config.json` |
| Canonical interface | `utils/config.py` (tenant helpers) + `utils/api_branding.py` (HTTP surface) |
| Consumers | `frontend/web/src/providers/BrandingProvider.tsx` (via `GET /api/branding`); every Streamlit page (via `utils/config`) |
| Conflict rule | `data/org_config.json` always wins. Brand strings in code (e.g. "Ecobank Kenya") are violations of G381 / `gate_tenant_identity_hardcoding`. |
| Enforcement | `gate_tenant_identity_hardcoding` (line 20576), G381 (App.tsx contract), G382 (no hardcoded hex in components) |
| Owner | Admin / Tenant Onboarding |
| Classification | `canonical` |

---

### Domain: Role taxonomy & RBAC

| Field | Value |
|---|---|
| Authoritative source | `data/org_hierarchy_config.json` |
| Canonical interface | `utils/role_taxonomy.py` (exports: `classify_role`, `get_profitability_tier`, `get_branch_scope`, `get_sbu`, `can_be_tagged`, plus tier/SBU/scope constants) |
| Consumers | `utils/auth_jwt.py::require_role` *(transitional — currently takes raw role strings; canonical contract is via role_taxonomy)*; `utils/hierarchy_synth.py`; `utils/profitability_hierarchy.py`; `utils/cascade_hierarchy.py`; `utils/staff_role_resolver.py`; `data/users.json` role field; `data/hr.json` role field |
| Conflict rule | `org_hierarchy_config.json::profitability_axis.role_classification` is exhaustive; roles not present there must classify via `tier_keyword_fallback`. If neither resolves, classification defaults to `support` + warning. Drift is the registry being silently inconsistent — it must be reconciled at the source file, not papered over in consumers. |
| Enforcement | **G260** (`gate_role_taxonomy_alignment`, line 36381) — verifies module exports, config integrity, 100% role coverage, taggability invariants. |
| Owner | Admin / HR Operations |
| Classification | `canonical` |
| Notes | Per `_v10398_joshua_hq_canonical` (2026-05-13): every HQ role mapped to a Chief. Per `_v10330_canonical_retail_chain`: retail chain locked. The role taxonomy is **load-bearing data**, not implementation detail. |

---

### Domain: Authentication & session tokens

| Field | Value |
|---|---|
| Authoritative source | `utils/auth_jwt.py` (post v10.497 P1.3) |
| Canonical interface | Exports `get_current_user`, `create_access_token`, `decode_token`, `revoke_token`, `_is_revoked`, `require_admin`, `require_role` |
| Consumers | `utils/api.py` (all endpoints except `/api/health`); future `frontend/web/src/providers/AuthProvider.tsx` (via cookie) |
| Conflict rule | **Bearer Authorization header only.** Cookie-based auth was never implemented in production (the v10.497 P1.3 cookie proposal was rolled into the React substrate work but the AuthProvider lifecycle adopted Bearer-header-only per v10.500 Phase 1 Batch 3a, commit `13d5258`). CSRF is N/A for the Bearer model. Blocklist check fires after signature/expiry validation. No alternate JWT issuance paths permitted. *(Corrected v10.502 Stage C Arc D2 Batch 5b — cross-ref GOVERNANCE_REALITY_INDEX Batch 3d React substrate correction.)* |
| Enforcement | **G12** (`gate_api_auth_safety`, line 811) — every endpoint except `/api/health` declares an auth Depends. |
| Owner | Security / Platform |
| Classification | `canonical` (post v10.497 P1.3) |
| Critical drift to flag | **RESOLVED.** `utils/auth.py` (Streamlit-era) previously exported a function also named `require_role(module, user)` taking a module-string — colliding with the `auth_jwt.py::require_role(roles: list[str])` factory. In v10.498 Stage C Batch 1b the Streamlit alias was renamed to `require_module_access` (commit `2bcd76f`, enforced by G383 `gate_v10498_no_require_role_collision`). The name space is now clean. *(Corrected v10.502 Stage C Arc D2 Batch 5b.)* |

---

### Domain: Streamlit-era page-access RBAC

| Field | Value |
|---|---|
| Authoritative source | `utils/auth.py` |
| Canonical interface | `require_access(module)`, `has_access(module)`, `is_admin()`, plus alias `require_role` (collides by name with `auth_jwt.require_role`) |
| Consumers | Streamlit `pages/*.py` (158 pages per Master Prompt v5.40) |
| Conflict rule | Checks `user.accessible_modules`, `user.hidden_modules`, `user.is_admin`, `user.is_ict_admin`, `user.can_view_all` from `data/users.json`. |
| Enforcement | None mechanical at scale today (no gate dedicated to page-access coverage in scripts/audit.py grep). |
| Owner | Admin / Platform |
| Classification | `transitional` — Streamlit will be progressively replaced by React (post v10.500 per Master Prompt). The page-access model needs to be reconciled with React's `AuthProvider` + `ProtectedRoute` contract in Wave 2. Once reconciled and React-fronted, this becomes `canonical` for the duration of the Streamlit migration; afterward `deprecated`. |
| Notes | The name collision between `utils/auth.require_role` (module-string, returns bool) and `utils/auth_jwt.require_role` (list[str] factory, returns Depends) is a constitutional violation that Wave 2 must resolve. **Recommendation (provisional):** rename `utils/auth.py::require_role` → `utils/auth.py::require_module_access` to disambiguate. Resolution requires touching every Streamlit page that imports it. |

---

### Domain: User identity & seed data

| Field | Value |
|---|---|
| Authoritative source | `data/users.json` (1,439 records as of 2026-05-22) |
| Canonical interface | `utils/core.py::UserManager` (`authenticate`, lookup, role/department/staff_code resolution) |
| Consumers | `utils/auth.py::has_access`; `utils/auth_jwt.py::create_access_token`; every page/route that resolves a user |
| Conflict rule | `users.json` wins. **Passwords are bcrypt envelope `bcrypt(sha256_hex)` for all 1,437 records** (migration completed v10.500 Phase 1 Batch 3c at commit `216171d`; `scripts/verify_bcrypt.py` enforces the envelope shape). *(Corrected v10.502 Stage C Arc D2 Batch 5b — was previously "SHA-256 today with bcrypt migration on successful login" reflecting pre-3c state.)* |
| Enforcement | `gate_password_safety` (line 741); `gate_validate_password_policy` (closes GAP-001 + GAP-005 via tests/test_validate_password_policy.py, v10.501 Phase 2 Arc A); `gate_rate_limit_auth` (closes GAP-006 via tests/test_rate_limit_auth.py, v10.501 Phase 2 Arc B). Schema-level gate over users.json shape remains TBD — Wave 2 RBAC_MATRIX scope. |
| Owner | HR Operations / Admin |
| Classification | `canonical` (bcrypt migration complete; password policy enforced; rate limiting active) |

---

### Domain: KPI library & role-KPI mapping

| Field | Value |
|---|---|
| Authoritative source | `data/kpi_library.json` |
| Canonical interface | `utils/kpi_alias_resolver.py`, `utils/kpi_aggregation_rules.py`, `utils/kpi_dedup_engine.py`, `utils/kpi_ownership.py` |
| Consumers | `utils/bsc_engine.py` family (11 BSC modules); `utils/cascade_*` (8 cascade modules); every actuals engine |
| Conflict rule | Canonical KPI IDs in `kpi_library.json::kpis` win. Aliases (descriptive names, short codes) resolve via `kpi_alias_resolver`. The `_v10469_role_kpis_resolution` block declares `1469 resolved, 0 unresolved`. |
| Enforcement | `gate_kpi_alias_resolver` (line 37361); `gate_kpi_alias_and_users_cleanup` (line 30755); `gate_canonical_pillar_weights` (line 37965); `gate_universal_bsc_contract` (line 36805); `gate_kpi_source_has_aggregator` (line 18333) |
| Owner | Performance / BSC governance |
| Classification | `canonical` |

---

### Domain: Org hierarchy synthesis

| Field | Value |
|---|---|
| Authoritative source | `data/org_hierarchy_config.json` (same file as role taxonomy; different sub-trees) |
| Canonical interface | `utils/hierarchy_synth.py`, `utils/org_hierarchy_config.py`, `utils/cascade_hierarchy.py`, `utils/profitability_hierarchy.py` |
| Consumers | `data/users.json` (manager assignments derived); `utils/core.py::ReportingLineManager`; `utils/cascade_bsc_*` |
| Conflict rule | `hr.json` source-data linkages that violate `role_manager_whitelist` are flagged and replaced with synthesis-derived linkages. Synthesizer is authoritative for the final org tree. |
| Enforcement | `gate_hierarchy_classification_correct` (line 3034); `gate_hierarchy_synth` (line 28575); `gate_hierarchy_synth_config` (line 28752); `gate_canonical_retail_chain` (line 31416); `gate_cascade_hierarchy_alignment` (line 29144); `gate_target_hierarchy` (line 36243) |
| Owner | Admin / HR Operations |
| Classification | `canonical` |

---

### Domain: BSC scoring & cascade

| Field | Value |
|---|---|
| Authoritative sources | `data/bsc_data.json` (current period staff KPIs); `data/bsc_scores.json` (computed); `data/bsc_actuals_*.json` (per-period historical, 8 periods); `data/cascade_scores_*.json` (4 periods); `data/bank_targets.json` (top-level); `data/target_cascade.json` (per-staff cascade); `data/locked_targets.json`; `data/pillar_weights_history.json`; `data/fixed_kpis.json` |
| Canonical interface | `utils/bsc_engine.py`, `utils/bsc_score_computation.py`, `utils/bsc_universal_contract.py`, `utils/canonical_bsc_writer.py`, `utils/canonical_pbt_bsc_view.py`; `utils/core.py::CascadeManager` |
| Consumers | All BSC dashboards (Streamlit + React future); MD cockpit; cascade UI; PM framework |
| Conflict rule | Hierarchy: `fixed` KPI value → cascaded value → role default target → missing. `kpi_library.json` is canonical for KPI definitions; `bsc_data.json` is canonical for assignments; `bank_targets.json` is canonical for top targets; `target_cascade.json` is canonical for per-staff distribution. |
| Enforcement | `gate_bsc_contract` (line 441); `gate_bsc_completeness/audit`; `gate_bsc_score_computation` (line 29445); `gate_canonical_write_bridge` (line 37182); `gate_universal_bsc_contract` (line 36805); plus 8+ v1 audit endpoints under `/api/v1/bsc-*/` |
| Owner | Performance / BSC governance |
| Classification | `canonical` |

---

### Domain: API surface

| Field | Value |
|---|---|
| Authoritative source | `utils/api.py` + mounted routers: `utils/api_branding.py`, `utils/api_cascade.py`, `utils/api_capacity_feedback.py`, `utils/api_compliance.py`, `utils/api_legal.py`, `utils/api_telemetry.py`, `utils/api_treasury.py`, `utils/api_strategy.py`, `utils/api_product.py`, `utils/api_resource_optimization.py`, `utils/api_cockpit.py`, `utils/api_crud.py`, `utils/api_gateway_developer_portal.py` |
| Canonical interface | FastAPI route declarations with `Depends(get_current_user)` (auth) or `Depends(require_admin)` (admin only) or `Depends(require_role(...))` (role-gated, factory) |
| Consumers | Test scripts (`scripts/run_load_tests.py`); load test infrastructure (`tests/load/lib/auth.js`); future React frontend (`frontend/web/src/lib/api.ts`); Streamlit pages calling `utils/api_client.py` |
| Conflict rule | Every endpoint except `/api/health` must declare an auth Depends. State-changing endpoints must emit an `_audit()` event. |
| Enforcement | **G12** (`gate_api_auth_safety`, line 811); `gate_api_v1_coverage` (line 1249); `gate_audit_coverage` (line 251); `gate_cors_and_deploy_config` (line 26146); `gate_cockpit_api_exposed` (line 25835) |
| Owner | Platform |
| Classification | `canonical` with a `transitional` sub-area: destructive admin endpoints today are gated by `confirm: bool = False` query param, not RBAC. Wave 2 RBAC_MATRIX must classify which of these need genuine role-gating. |

---

### Domain: Telemetry & audit

| Field | Value |
|---|---|
| Authoritative source | `utils/api.py::_audit` (single emitter at line 170); broader observability via `utils/observability_monitoring.py`, `utils/api_telemetry.py`, `utils/anomaly_observer.py`, `utils/event_bus.py`, `utils/cross_organ_event_bus.py` |
| Sinks | `data/audit_log.json` (append-only); `data/audit_trail.jsonl` (line-delimited); `data/audit_baselines.json`; `data/audit_reviews.json`; `data/observability_metrics.json` |
| Consumers | Audit dashboards; compliance reports; G260+ verifier; `/api/v1/vitals/*` endpoints |
| Conflict rule | `_audit()` is the only legitimate emitter for API audit events. Engine modules emit via their own audit log convention but should converge on the same event_bus pipeline. |
| Enforcement | `gate_audit_coverage` (line 251) verifies state-changing endpoints emit `_audit()`. |
| Owner | Compliance / Audit |
| Classification | `canonical` (API audit) + `transitional` (broader observability — multiple modules suggest evolution in progress; Wave 4 TELEMETRY_MAP will surface) |

---

### Domain: Frontend governance

| Field | Value |
|---|---|
| Authoritative source | **ACTIVE:** `frontend/web/src/lib/tokens.ts` (semantic hex tokens); `data/org_config.json` (brand colors via API); `frontend/web/tailwind.config.js` (Tailwind extends); `frontend/web/src/index.css` (CSS variable bindings). **ASPIRATIONAL** (pending shadcn pivot completion): `frontend/web/components.json`. *(Split corrected v10.502 Stage C Arc D2 Batch 5b — cross-ref GOVERNANCE_REALITY_INDEX Batch 2a-shadcn correction.)* |
| Canonical interface | **ACTIVE:** A2Z bespoke React primitives under `frontend/web/src/components/` (BrandingProvider, AuthProvider, ProtectedRoute, useRole, App.tsx contract). **ASPIRATIONAL** (pending shadcn pivot completion): shadcn/ui primitives under `frontend/web/src/components/ui/*`; `lib/cn` utility for class composition. The shadcn pivot was attempted in v10.497 P0, rolled back by v10.499 Stage C Batch 2a; bespoke implementation is the current ACTIVE form. |
| Consumers | Every React page and component under `frontend/web/src/pages/*` and `frontend/web/src/components/*` |
| Conflict rule | `tokens.ts` is single source for semantic hex. Brand color variables (`--brand-*`) are HEX, tenant-injected via BrandingProvider. shadcn theme variables (HSL components derived from `tokens.ts`) become ACTIVE only when the shadcn pivot is re-attempted. No hardcoded hex elsewhere. |
| Enforcement | **G381** (App.tsx contract literals preserved); **G382** (all primitives exist, Dashboard uses them, no hardcoded hex in `src/components/**.tsx`); `gate_frontend_scaffolding_present` (line 4111); `gate_v10495_react_foundations` (line 58961); `gate_v10496_design_system` (line 59116) |
| Owner | Frontend / Design system |
| Classification | `canonical` (bespoke React primitives layer; shadcn pivot remains ASPIRATIONAL post-rollback) |

---

### Domain: Digital twin / virtual bank simulation

| Field | Value |
|---|---|
| Authoritative source | Generator scripts at project root (`generate_cbs.py`, `generate_staff.py`, `compute_actuals.py`); `utils/virtual_bank_*.py` family (8 modules); `data/cbs_baseline_*.json` |
| Canonical interface | `utils/virtual_bank_core.py`, `utils/virtual_bank_simulator.py`, `utils/vb_actuals_bridge.py`, `utils/virtual_bank_kpi_unifier.py` |
| Consumers | CBS explorer page (Streamlit); future React CBS view; actuals engines |
| Conflict rule | Generated baseline persists in `cbs_baseline_*.json` and `branch_actuals.json`. Live actuals overlay via `utils/live_actuals.py`. Manual overrides via BSC Excel upload act as override path. |
| Enforcement | `gate_cbs_baseline` (line 34026); `gate_cbs_writer_integrity` (line 34539); `gate_virtual_bank_readiness` (line 34337); `gate_virtual_bank_foundation` (line 28413); `gate_virtual_bank_simulation_implemented` (line 15188); `gate_seed_determinism` (line 34424) |
| Owner | Simulation / Training |
| Classification | `canonical` |

---

### Domain: AI / ML governance

| Field | Value |
|---|---|
| Authoritative source | `utils/model_governance.py`, `utils/model_governance_runtime.py`, `utils/mlops_model_registry.py`, `utils/mlops_model_card_composer.py`, `utils/mlops_adjudication_log.py`, `utils/mlops_ab_harness.py`, `utils/mlops_retraining_scheduler.py`, `utils/mlops_persistence.py`, `utils/ai_explainability.py`, `utils/ai_underwriting.py`, `utils/fairness_testing.py` |
| Canonical interface | Model registry (versioned model cards); AB harness; adjudication log; retraining scheduler |
| Consumers | Every engine that uses ML inference (`utils/credit_alt_scoring.py`, `utils/decline_prediction.py`, `utils/churn_prediction.py`, `utils/customer_predictive_*`, `utils/predictive_*`); cross-sell bandit |
| Conflict rule | Models must be registered before deployment. Predictions emit adjudication log entries. AB harness controls rollouts. Retraining scheduler is the only canonical retraining trigger. |
| Enforcement | `gate_model_governance_engines_implemented` (line 14969); `gate_ml_governance_arc_closed` (line 17765); `gate_ml_governance_arc_ui_integrated` (line 17977); `gate_ml_governance_cross_platform_wiring` (line 18100); `gate_anti_drift_completion_floor` (line 18223); `gate_cross_sell_bandit_pilot_implemented` (line 15376) |
| Owner | ML governance / Model risk |
| Classification | `canonical` |
| Notes | Wave 5 will produce `AI_GOVERNANCE.md` with full model lifecycle documentation. Stage A did not survey these modules in detail. |

---

### Domain: Resilience & certification

| Field | Value |
|---|---|
| Authoritative source | `utils/enterprise_discharge_audit.py`; `utils/audit_trail_certification.py`; `utils/audit_trail_cert.py`; `utils/disaster_recovery.py`; `utils/it_disaster_recovery.py`; `utils/it_cicd.py`; `utils/scalability_validator.py`; `utils/stress_test_harness.py`; `utils/stress_testing.py`; `utils/chaos/` (subdirectory) |
| Canonical interface | Discharge audit; certification ledger; DR/BCP playbooks; chaos engineering harness |
| Consumers | Audit dashboards; regulatory submissions; board reports |
| Conflict rule | Certification states are append-only (revival ledger semantics). Stress tests with passing thresholds are required for certification. DR drills produce audit trail entries. |
| Enforcement | `gate_enterprise_discharge_audit` (TBD specific line); `gate_v10471_enterprise_discharge_ready` (line 53895); `gate_v10472_enterprise_360_compliance` (line 54016); `gate_v10473_o1_stabilization_complete` (line 54119); `gate_v10487_olympic_certification` (line 57583); `gate_v10488_championship_readiness` (line 57807); `gate_v10482_o5_chaos_engineering` (line 56093); 6 uncertainty-exposure gates (v10489–v10494) |
| Owner | Operations / Risk / Audit |
| Classification | `canonical` |
| Notes | Wave 5 will produce `RESILIENCE_AND_CERTIFICATION_GOVERNANCE.md`. The "Olympic certification" and "championship readiness" gates indicate a maturity-level framework that needs explicit documentation. |

---

### Domain: Audit gates (the enforcer of enforcement)

| Field | Value |
|---|---|
| Authoritative source | `scripts/audit.py` |
| Canonical interface | `run_all(only_gate)`, `render_human(report)`, `main()` |
| Consumers | CI/CD pipeline; pre-commit checks (TBD); manual `python -m scripts.audit` runs |
| Conflict rule | A gate is canonical if (a) it has a name matching `gate_<topic>_<verb>` or `gate_v10XXX_<topic>` and (b) it returns the standard `{id, name, passed, violations, summary}` dict. Versioned batch gates (`gate_v10XXX_*`) persist after their batch as load-bearing checks. |
| Enforcement | Self-verification: `gate_audit_coverage` (line 251); the verifier (1153/1153 status reported in Master Prompt v5.40) is the broader system that runs all gates. |
| Owner | Doctrine / Architecture |
| Classification | `canonical` |
| Notes | As of v10.497 governance batch: **412 distinct gate functions** (271 canonical-named + 147 versioned batch). Wave 1 adds a new gate: `gate_canonical_truth_registry_sync` (placeholder; written in Stage C). |

---

### Domain: Constitution itself

| Field | Value |
|---|---|
| Authoritative source | `docs/architecture/CANONICAL_TRUTH_REGISTRY.md` (this file) + `.json` machine-readable companion |
| Canonical interface | This document. Future automation may parse `.json`. |
| Consumers | Future AI sessions (read this first); audit gate `gate_canonical_truth_registry_sync` (Stage C); human collaborators making architectural decisions |
| Conflict rule | If a domain claims authority elsewhere without being listed here, this registry must be updated *first*. PRs that add a new authoritative source without updating this registry fail audit. |
| Enforcement | `gate_canonical_truth_registry_sync` (Stage C, TBD) — verifies every domain referenced in audit gates appears here with consistent pointers. |
| Owner | A2Z constitution maintainers |
| Classification | `canonical` |
| Versioning | This document uses semantic versioning. Major version increments on breaking authority changes (e.g. JSON → PostgreSQL migration). Minor on new domain entries. Patch on clarifications. |

---

## Conflict-resolution flowchart

When tools or sessions encounter divergence between two files:

```
1. Look up the domain in this registry.
2. Read the "Authoritative source" — that file's content is truth.
3. Read the "Consumers" — those files must conform to source.
4. If a consumer disagrees with source:
   → Source wins.
   → File the consumer drift as an issue.
   → Open a remediation batch.
5. If no domain matches the conflict:
   → This is a constitutional gap.
   → Add the domain to this registry before resolving.
```

This rule has one exception: **a session or tool MAY override conflict resolution if** the change has been explicitly authored as a governance batch (e.g. v10.398 Joshua HQ canonical batch). In that case the source itself is being updated; the consumers will be reconciled in subsequent commits.

---

## Adding a new domain

To add a new architectural domain to this registry:

1. Draft a `## Domain: <name>` section with all required fields
2. Identify or create the authoritative source file
3. Write or update the audit gate that enforces it
4. Update `CANONICAL_TRUTH_REGISTRY.json` in the same commit
5. Run `gate_canonical_truth_registry_sync` to verify pointer consistency
6. Append to `REVIVAL_LEDGER.md` with date and rationale

No domain may be added without all six steps. Drift prevention starts with disciplined inclusion.

---

## Open items (transitional, to be resolved in subsequent waves)

These are flagged here because they will inform the artifacts written in Waves 2-6:

1. **`require_role` name collision** between `utils/auth.py` (Streamlit module-string) and `utils/auth_jwt.py` (FastAPI list[str] factory). Resolution path: rename Streamlit's to `require_module_access`. Wave 2 RBAC_MATRIX will declare the rename.

2. **v1 admin endpoint RBAC**: 53 v1 endpoints declared with `Depends(get_current_user)` but no `require_admin` or `require_role`. Destructive operations rely on `confirm: bool = False` query param. Wave 2 API_CONTRACTS will classify each as either (a) authenticated-user is sufficient, (b) needs `require_admin`, or (c) needs specific `require_role([...])`.

3. **Streamlit → React migration**: Master Prompt v5.40 declares 158 Streamlit pages. The page-access RBAC in `utils/auth.py` is `transitional` pending React replacement. Wave 2 will declare the migration contract.

4. **AI/ML governance & resilience domains**: Wave 5 will produce dedicated artifacts. They are listed here at high level only.

5. **CHANGELOG governance**: `docs/CHANGELOG_*.md` and `docs/releases/*.md` are empty. CHANGELOG_MASTER (Wave 6) will define the per-version detail format and seed it from `scripts/audit.py` versioned batch gates.

---

**End of CANONICAL_TRUTH_REGISTRY.md**
