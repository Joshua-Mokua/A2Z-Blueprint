# A2Z Blueprint MIS 360 — System Constitution

**Type:** Constitutional artifact, foundational principles
**Authority level:** Constitution
**Status:** `canonical`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 1)
**Last updated:** 2026-05-22
**Owner:** A2Z constitution maintainers (Joshua + designated reviewers)
**Machine-readable equivalent:** `SYSTEM_CONSTITUTION.json`
**Companion artifacts:** `CANONICAL_TRUTH_REGISTRY.md`, `GOVERNANCE_CLASSIFICATION_REGISTRY.md`

---

## Preamble

A2Z Blueprint MIS 360 is the bank's operating organism. It does not exist to display numbers. It exists so a Managing Director, a Branch Manager, a Relationship Officer, a Credit Analyst, and a Teller each make better decisions today than they made yesterday. Every architectural choice — every module, every endpoint, every gate, every line of frontend code — must serve that purpose or be a violation of this constitution.

This document captures the principles that have emerged from 141+ consecutive lockstep batches of harmonization, certification, and revival. It is not a wish-list. It is the **load-bearing doctrine** that the system already enforces through 412 audit gates. This document records what the gates enforce, what the data structures already canonicalize, and what the next phases must continue to honor.

Future AI sessions, human collaborators, and audit tooling read this first. Then they read `CANONICAL_TRUTH_REGISTRY.md` for the specific authoritative sources. Then they read the domain-specific governance artifacts. Then — and only then — do they make architectural decisions.

---

## Article I — The system is a living organism

### §1.1 Organic metaphor as design discipline

The system is described as an **organism** with **organs**, **vital signs**, **certification states**, and **discharge readiness**. This is not metaphor for marketing. It is a **design discipline**:

- Every major capability is an **organ** (a `Manager` class, an `_engine.py` module, or a coherent module family) with declared **responsibilities**, **dependencies**, **inputs**, and **outputs**
- Organs have **vitals** — `/api/v1/vitals/full`, `/organs`, `/regression` — that report health
- Organs have **certification** — they progress through readiness milestones (`enterprise_discharge_ready`, `enterprise_360_compliance`, `olympic_certification`, `championship_readiness`)
- Organs interconnect through a **cross-organ event bus** (`utils/event_bus.py`, `utils/cross_organ_event_bus.py`)

This discipline means: **every architectural decision asks "which organ does this belong to, and what is its contract with the rest of the body?"** Code that doesn't belong to any organ is a violation. Code that violates an organ's contract is a violation. Code that creates a new organ without declaring its contract is a violation.

### §1.2 Operational resilience is not optional

The body must function under stress. This means:

- **Chaos engineering** (`gate_v10482_o5_chaos_engineering`) exists and runs
- **Stress testing** (`gate_stress_test_returns_correct`, `gate_v10458_stress_scalability`) is part of the audit gate suite
- **Disaster recovery** (`utils/disaster_recovery.py`, `utils/it_disaster_recovery.py`) is a first-class concern
- **Uncertainty exposure** (six phases, `gate_v10489` through `gate_v10494_FINAL`) probes the limits of system trust

Resilience requirements are codified in `RESILIENCE_AND_CERTIFICATION_GOVERNANCE.md` (Wave 5).

---

## Article II — Single source of truth per concern

### §2.1 Authority is non-overlapping

For every architectural domain, exactly one file or module **defines** truth. Multiple files may **consume** that truth. The authoritative source is declared in `CANONICAL_TRUTH_REGISTRY.md`.

When a consumer's behavior disagrees with the source, the **source wins**. The consumer is reconciled, not the other way around. The only exception is an explicit governance batch updating the source itself (e.g. `_v10398_joshua_hq_canonical`).

### §2.2 The canonical interface

Every authoritative source has a **canonical interface** — a Python module, a FastAPI router, a JSON schema — that consumers must use. Direct file reads from outside the canonical interface are violations.

Examples currently enforced:

| Authority                        | Canonical interface                    | Violation pattern (forbidden)                      |
| -------------------------------- | -------------------------------------- | -------------------------------------------------- |
| `data/org_hierarchy_config.json` | `utils/role_taxonomy.py`               | Parsing role strings directly in arbitrary modules |
| `data/users.json`                | `utils/core.py::UserManager`           | Reading `users.json` directly outside UserManager  |
| `data/kpi_library.json`          | `utils/kpi_alias_resolver.py` + family | Hardcoded KPI ID lists in route bodies             |
| JWT tokens                       | `utils/auth_jwt.py`                    | Decoding tokens with custom code                   |
| Tenant identity                  | `utils/config.py` + `/api/branding`    | Hardcoded "Ecobank" in any code                    |

### §2.3 Multi-tenancy from day one

Tenant identity (bank name, regulator, brand colors, IP notice) lives entirely in `data/org_config.json` and flows to consumers via `/api/branding` (React) or `utils/config.py` (Streamlit). **No tenant string in any code, anywhere.** Enforced by `gate_tenant_identity_hardcoding` (CRITICAL severity), G381 (frontend), and G382 (design tokens).

---

## Article III — Canonical role governance

### §3.1 Two orthogonal axes

Every role in the system is classified on two **orthogonal** axes:

**Seniority axis** (`role_tiers`, 0-6):

- 0 = MD root
- 1 = C-suite + Directors
- 2 = Head Of / Regional Head
- 3 = Senior Manager / Area Manager
- 4 = Manager / Branch Manager
- 5 = Officer / Specialist / RM
- 6 = Teller / CSO / DSR / Trainee

**Profitability axis** (`profitability_axis.tiers`, 5 categories):

- `portfolio_owner` — tagged to customers, drives sales
- `proposition_owner` — drives overlap proposition, NOT tagged
- `structural_owner` — owns PBT at structural level
- `service` — branch ops, occasionally tagged
- `support` — head office function

The axes are orthogonal: a `Branch Manager` is seniority tier 4 AND profitability `structural_owner`. Both classifications are required for every role.

### §3.2 The canonical resolution path

The **only** legitimate way to make a decision based on a role is to call into `utils/role_taxonomy.py`. Specifically:

- `classify_role(role_string)` returns a `RoleClassification` dataclass with tier, branch_scope, sbu, and how it matched
- `can_be_tagged(role_string)` is the **only** authority on whether a role may appear in `accounts.csv::relationship_manager_code`
- `get_profitability_tier`, `get_branch_scope`, `get_sbu` are the convenience accessors

**Hardcoded role string lists in route bodies, page logic, or React conditional rendering are violations** of this article. The constitution permits raw role strings only in two places:

1. Inside `utils/role_taxonomy.py` itself (the canonical implementation)
2. As display strings in user-facing UI (where the canonical resolution has already happened)

### §3.3 Hierarchy invariants

The org hierarchy obeys these invariants (declared in `org_hierarchy_config.json::_validation_rules`):

- **`exactly_one_root_required`** — one and only one MD
- **`no_cycles_allowed`** — the reporting graph is a tree
- **`only_chiefs_report_to_md`** — depth-1 from root is C-suite only
- **`every_staff_has_a_chain_to_root`** — no orphans

Plus:

- `default_max_span_of_control: 15`
- `default_max_chain_depth: 12`

`gate_role_taxonomy_alignment` (G260) and `gate_hierarchy_synth` enforce these continuously.

### §3.4 Joshua-authored canonical batches are load-bearing

Specific harmonization decisions recorded by Joshua are constitutional:

- **`_v10330_canonical_retail_chain`** — Retail chain locked: BM → Area Manager → Head of Branches → CRBO. SBM peer to BM, not supervisor.
- **`_v10396_joshua_clarification`** — Branch structure: BM/SBM at top; BOM/BRM/BSRO/RO PB/RO BB/DSR report to BM/SBM; BOS/Teller/CSO report to BOM.
- **`_v10398_joshua_hq_canonical`** — Every HQ role mapped to a Chief. 103 roles added, 127 tier updates.
- **`_v10399_joshua_corrections`** — 7 specific corrections including synthetic MD deletion and DFS head migration CIO→CCO.
- **`_v10469_role_kpis_resolution`** — All 1,469 role-KPI references resolved to canonical IDs. Zero unresolved.

Reverting any of these requires an explicit governance batch with full rationale, not silent code changes.

---

## Article IV — Engine purity

### §4.1 Engines are pure-compute; transports are thin

The system has two **transport layers** (Streamlit pages, FastAPI routes) and one **compute layer** (engines under `utils/`). The rule:

- **Engines** (`_engine.py` modules, `Manager` classes) contain business logic and data computations. They have **no awareness** of which transport calls them.
- **Transports** (Streamlit pages, FastAPI route handlers) translate between user/HTTP requests and engine calls. They contain **no business logic** beyond request validation.

This means **the same engine is callable from Streamlit and FastAPI**, producing identical results. A test that exercises an engine doesn't need to spin up either transport.

Violations:

- Business rules embedded in route handlers (e.g. `if user.role == "MD": ...` instead of calling into `role_taxonomy`)
- Engines importing Streamlit or FastAPI
- Engines using `st.session_state` or `Request` objects

### §4.2 Audit gates are part of the compute contract

Every engine must have at least one audit gate verifying its declared contract. Gates live in `scripts/audit.py` and follow the naming convention `gate_<domain>_<verb>` or `gate_v10XXX_<topic>` for versioned batch gates.

A gate returns:

```python
{
    "id": "GXXX",
    "name": "gate_<topic>",
    "passed": bool,
    "violations": list[str],
    "summary": str
}
```

**Gates are the system's immune cells.** They detect drift continuously. When a gate fails, it is not a notification — it is a constitutional violation requiring remediation.

---

## Article V — Authentication and authorization

### §5.1 Every endpoint declares its auth posture

Every FastAPI endpoint except `/api/health` MUST declare one of:

- `Depends(get_current_user)` — any authenticated user
- `Depends(require_admin)` — admin role required
- `Depends(require_role([...]))` — specific role list required (v10.497 addition)

`/api/health` is the **only** unauthenticated route. It returns liveness information without any session lookup.

Enforced by **G12** (`gate_api_auth_safety`).

### §5.2 JWT tokens are the canonical session

JWT (HS256, 30-minute lifetime) is the canonical session token. Claims:

- `sub` (username)
- `role` (role string — transitional; canonical contract is to resolve via `role_taxonomy` at the consumer)
- `iat`, `exp`
- `jti` (UUID4, v10.497 addition, enables blocklist)

Tokens are sourced from either an `access_token` httpOnly cookie OR an `Authorization: Bearer <token>` header. **Cookie wins when both present.** Set by `/api/auth/login`. Cleared and blocklisted by `/api/auth/logout`.

### §5.3 Logout is regulator-grade

Logout MUST do both:

1. Clear the auth cookie client-side (`response.delete_cookie`)
2. Add the token's `jti` to the blocklist with TTL = remaining lifetime

A token that has been logged out MUST be rejected by `decode_token` on every subsequent request until natural expiry — even when its signature is valid.

### §5.4 The `require_role` name collision

`utils/auth.py` (Streamlit-era) exports `require_role(module, user) -> bool` for page-access checking. `utils/auth_jwt.py` (v10.497) exports `require_role(roles: list[str])` as a FastAPI Depends factory.

This is a **constitutional violation by name collision**. It will be resolved by renaming `utils/auth.py::require_role` to `require_module_access` in Wave 2 of the governance batch. Until that resolution, this collision is marked `transitional` in `CANONICAL_TRUTH_REGISTRY.md` with severity `HIGH`.

### §5.5 V-003 password fix

Passwords are stored as bcrypt hashes. New accounts get bcrypt directly. Existing accounts with SHA-256 hashes migrate to bcrypt transparently on successful login (`UserManager.authenticate` handles this). Plain-text or unsalted password storage is a **CRITICAL** violation.

---

## Article VI — Data dictionary discipline

### §6.1 Every persistent file has an owner

Every file in `data/` is owned by a specific module or team. Ownership is declared in `CANONICAL_TRUTH_REGISTRY.md` and `DATA_DICTIONARY.md` (Wave 4).

### §6.2 Schemas where they exist; ad-hoc otherwise

The system currently has `data/_schemas/` for some files. Where a schema exists, it is canonical for the file's shape. Where no schema exists, the consuming module's parsing code is the de facto contract (with an open item to formalize).

### §6.3 Backups and retention

Backup directories use the pattern `data/_v10XXX_backups/`. Retention policy is enforced by `/api/v1/backup-retention/audit` and the corresponding apply endpoint. Backup directories are gitignored.

---

## Article VII — Frontend governance

### §7.1 Single component system

The frontend uses **shadcn/ui** as its single governed component system (effective v10.497 Phase 0). No parallel component architectures. No bespoke primitives competing with shadcn-installed equivalents.

A2Z banking-grade extensions exist:

- `Button.loading` prop (universal form-submit affordance)
- `Badge.tone` variants (semantic operational signaling)
- `StatCard` composition over shadcn `Card` (KPI tile pattern)

These extensions are documented in `FRONTEND_GOVERNANCE.md` (Wave 4). New A2Z extensions require justification and addition to this article.

### §7.2 Tokens flow from `tokens.ts`

`frontend/web/src/lib/tokens.ts` is the **single source of truth** for non-brand semantic hex colors. The CSS variables in `index.css` (shadcn theme) are HSL-component projections of tokens.ts hex values. The Tailwind config wraps these in `hsl(var(--token) / <alpha-value>)` for opacity support.

Brand colors (`--brand-primary`, `--brand-secondary`, `--brand-accent`) are HEX, tenant-injected at runtime by `BrandingProvider`. Tenant identity is **never** in code.

### §7.3 Role-driven rendering goes through a hook (future)

Phase 2 of v10.497 will introduce `useRole()` (or equivalent) that consumes the canonical role taxonomy via `/api/roles` (a future endpoint). React conditional rendering MUST use this hook, not direct role-string comparisons.

This contract will be declared in `FRONTEND_GOVERNANCE.md` (Wave 4) and enforced by a new gate added in Stage C.

---

## Article VIII — Audit trail and telemetry

### §8.1 Every state change is audited

Every state-changing operation in the API MUST emit an `_audit()` event (the single canonical emitter in `utils/api.py` line 170). Event types follow the convention `API_<DOMAIN>_<ACTION>` (e.g. `API_LOGIN_SUCCESS`, `API_CACHE_CLEAR`).

Audit log sinks:

- `data/audit_log.json` — append-only structured events
- `data/audit_trail.jsonl` — line-delimited equivalent

Enforced by `gate_audit_coverage`.

### §8.2 Beyond audit — observability

The system has a broader observability layer (`utils/observability_monitoring.py`, `utils/api_telemetry.py`, `utils/anomaly_observer.py`, `utils/event_bus.py`, `utils/cross_organ_event_bus.py`). The full contract will be documented in `TELEMETRY_MAP.md` (Wave 4).

### §8.3 No silent operations

Operations that change persistent state without emitting audit events are violations. Read-only operations need not emit events (per `gate_audit_coverage`).

---

## Article IX — AI and ML governance

### §9.1 Models are registered before deployment

Every ML model used in production must be registered in the model registry (`utils/mlops_model_registry.py`) with a model card (`utils/mlops_model_card_composer.py`). Predictions emit adjudication log entries (`utils/mlops_adjudication_log.py`). Rollouts are controlled by the AB harness (`utils/mlops_ab_harness.py`). Retraining is triggered only by the retraining scheduler (`utils/mlops_retraining_scheduler.py`).

### §9.2 Explainability and fairness

Models making decisions about humans (credit scoring, churn prediction, customer segmentation) must support explainability (`utils/ai_explainability.py`) and pass fairness testing (`utils/fairness_testing.py`) before deployment.

### §9.3 Anti-drift floor

Model accuracy drifting below declared thresholds triggers `gate_anti_drift_completion_floor`. Recovery is via retraining; if retraining fails, the model is taken out of service.

Full AI governance contract in `AI_GOVERNANCE.md` (Wave 5).

---

## Article X — Versioning and changelog

### §10.1 Two parallel version streams

- **Backend batches:** `v10.XXX` — current is v10.497
- **Master Prompt:** `v5.XX` — current is v5.40, will become v5.41 with this governance batch

Master Prompt updates at architectural inflection points, not every batch.

### §10.2 Lockstep discipline

The system has run **141+ consecutive lockstep batches** with `1153/1153` verifier checks passing. A "lockstep batch" is a unit of work that ships:

1. Engine module(s) with self-tests
2. Audit gate(s) added
3. Integration tests
4. Doc updates
5. Full verification (audit + integration suite) passing
6. Delivery (git commit; previously ZIP)

A batch that ships without all six is a **CRITICAL** constitutional violation.

### §10.3 Changelog as load-bearing artifact

Every batch produces a CHANGELOG entry. The aggregate is indexed in `CHANGELOG_MASTER.md` (Wave 6). Master Prompt versions are documented in their own files. Historical batch detail is recoverable from `scripts/audit.py` versioned batch gates (147 known).

---

## Article XI — Honest doctrine (carried from prior batches)

These principles are carried forward unchanged from prior Master Prompt versions:

### §11.1 Discovered prior work → honor not destroy

(From v10.495) If prior work exists, honor its contract. Refactor proves the abstraction; don't tear down what works to build what's prettier.

### §11.2 Phantom audit contracts → make real or remove

(From v10.496) If a gate references something that doesn't exist, either build the thing or remove the gate. Phantom references are constitutional rot.

### §11.3 No premature dependencies

(From v10.496) Don't install npm packages or Python libraries before they're needed. The v10.496 bespoke primitives existed precisely because shadcn/ui was premature at that point. v10.497 Phase 0 then pivoted to shadcn when it became appropriate. Both decisions were right at their moment.

### §11.4 Refactor proves the abstraction

(From v10.496) A design system isn't proven until at least two pages use it. Dashboard.tsx composed from primitives was the first proof. Showcase was the second. Every subsequent page extends the proof.

### §11.5 Honest assessment before mechanical execution

(Joshua's standing directive) Strategic proposals are reviewed critically before implementation. The drift detection that triggered this entire governance batch is the doctrine in action: stop, survey, codify, then proceed.

### §11.6 Mechanical enforcement over advisory documentation

(Joshua's standing directive) Quality is enforced by gates, not by docs alone. This constitution exists because gates exist; gates exist because they fail; failure forces remediation.

### §11.7 Autonomous continuation through declared scope

(Joshua's standing directive) Once a batch's scope is approved, the work proceeds without per-step approval. Approval points exist at scope inflection (start of wave, certification, merge). Mid-batch interruptions are reserved for genuine constitutional questions, not preferences.

---

## Article XII — Constitutional amendments

### §12.1 This document changes only by governance batch

Edits to this constitution MUST be made as part of a governance batch, never as a side effect of a feature commit. Governance batches:

1. Author the change in a feature branch (e.g. `feature/governance-constitution`)
2. Update `CANONICAL_TRUTH_REGISTRY.md` + `.json` to match
3. Add/modify the relevant audit gate(s)
4. Record the rationale in `REVIVAL_LEDGER.md`
5. Merge through `develop` → `main` with a `vX.YYY-constitutional` tag

### §12.2 The constitution is read-first

Future AI sessions, audit tooling, and human collaborators read:

1. **This file first** (principles, posture, doctrine)
2. **`CANONICAL_TRUTH_REGISTRY.md`** next (specific authoritative sources)
3. **`GOVERNANCE_CLASSIFICATION_REGISTRY.md`** for interpretation
4. **Domain-specific governance** (ROLE_GOVERNANCE, API_CONTRACTS, etc.) for details

Only then do they consider the question they came to answer.

### §12.3 Drift in the constitution itself

This constitution can drift — sections becoming aspirational rather than enforced. `gate_canonical_truth_registry_sync` (Stage C) verifies that this document and the canonical truth registry remain consistent. Drift between articles here and gates in `scripts/audit.py` is itself a violation.

---

## Closing

The body has organs. The organs have contracts. The contracts have gates. The gates produce certifications. The certifications carry forward as the body matures.

This constitution exists so that the next session, the next collaborator, the next migration, and the next decade of operational evolution can build on this foundation without rediscovering it.

The work continues.

---

---

## Article CGR1 — Constitutional Governance Reality-Grounding

**Status:** ACTIVE
**Introduced:** v10.498 Stage C Batch 1b
**Source incident:** G383's first-run output disproved a doctrine claim
**Enforcement:** GOVERNANCE_REALITY_INDEX.md (classification index)

### The principle

> **Constitutional governance must track runtime reality, not aspiration.**
> Every claim in `docs/architecture/` is classified ACTIVE, TRANSITIONAL,
> ASPIRATIONAL, or DEPRECATED. Audit gates enforce ACTIVE doctrine only.
> Aspirational claims are explicitly labeled, never enforced, and never
> conflated with current-state assertions.

### The four classifications

- **ACTIVE** — accurately describes deployed runtime; enforceable
- **TRANSITIONAL** — work-in-progress; partly true today; tracked path to ACTIVE
- **ASPIRATIONAL** — future-state; not enforceable; signpost for future batches
- **DEPRECATED** — was true, no longer; retained for history; scheduled removal

### Mechanics

Every artifact in `docs/architecture/` carries a classification banner at
the top. A new artifact, `GOVERNANCE_REALITY_INDEX.md`, catalogs every
artifact's overall classification and lists inline exceptions.

An audit gate MAY enforce a claim if and only if the claim's classification
is ACTIVE. Gates that test ASPIRATIONAL claims are constitutional theater
and MUST be either downgraded to TRANSITIONAL (visibility phase only) or
deferred until the implementation lands and the claim becomes ACTIVE.

### Discovery procedure

When a gate's first run reveals doctrine is wrong:

1. Don't blame the gate — the gate tested reality and reality won
2. Diagnose the doctrine (accidentally aspirational, was-true-now-false, or simply wrong)
3. Update classification (move the claim to ASPIRATIONAL, DEPRECATED, or delete)
4. Update the gate (tighten or retire)
5. Document the change in GOVERNANCE_REALITY_INDEX.md

The G383 incident in v10.498 Stage C Batch 1b is the canonical example
of this procedure.

### Standing principle

Henceforth, every constitutional artifact, every audit gate, every ledger
entry must answer: _Is this ACTIVE, or is this aspirational?_

A doctrine that cannot answer this question is incomplete. A gate that
enforces a non-ACTIVE claim is theater. An incident that reveals
reality-vs-doctrine drift is a feature of the system, not a failure.

**This is what makes governance trustworthy instead of ceremonial.**

**End of SYSTEM_CONSTITUTION.md**
