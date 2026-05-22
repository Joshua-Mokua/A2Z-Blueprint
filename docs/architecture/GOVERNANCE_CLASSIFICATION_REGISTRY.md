# A2Z Blueprint MIS 360 — Governance Classification Registry

**Type:** Constitutional artifact, meta-governance layer
**Authority level:** Constitution
**Status:** `canonical`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 1)
**Last updated:** 2026-05-22
**Owner:** A2Z constitution maintainers
**Machine-readable equivalent:** `GOVERNANCE_CLASSIFICATION_REGISTRY.json`
**Consumed by:** `CANONICAL_TRUTH_REGISTRY.md` (every domain has a `classification` field that must be one of the states defined here)

---

## Purpose

This registry defines:

1. **Governance classification states** — the lifecycle states any artifact, module, data source, or contract can be in: `canonical`, `derived`, `transitional`, `deprecated`, `unknown`.
2. **Enforcement tier taxonomy** — the severity bands that audit gates use to surface violations: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
3. **State transition rules** — how an artifact moves between states (e.g. `transitional` → `canonical`, `canonical` → `deprecated`).
4. **Rollout tolerance windows** — how long an artifact may remain in `transitional` before constitutional pressure escalates.

Per Joshua doctrine: **strict canonical governance with no tolerated drift** is the long-term target. This registry defines the bands that allow disciplined progress toward that target without operational paralysis during harmonization windows.

---

## Doctrine

**G1 — Every governed artifact has exactly one classification state.** No artifact can be simultaneously `canonical` and `transitional`. Sub-areas of an artifact may be transitional while the parent is canonical (see `canonical_with_transitional_subareas`).

**G2 — Classifications express intent and lifecycle, not quality.** A `canonical` artifact may still have bugs; a `transitional` artifact may work perfectly. The classification answers "what is the constitution's posture toward this?", not "how well does it work?"

**G3 — Transitions are events, not gradients.** An artifact transitions from `transitional` to `canonical` on a specific commit, with a date, rationale, and audit-gate sign-off recorded in `REVIVAL_LEDGER.md`. There is no fuzzy middle.

**G4 — Enforcement severity is independent of classification.** A `canonical` artifact violating its rules is a `CRITICAL` failure; a `transitional` artifact violating during a grace window may be `MEDIUM`. The two axes (classification × severity) are orthogonal.

**G5 — `unknown` is a temporary state, never a destination.** Anything classified `unknown` must move to one of the four real states within a specified resolution window (default 1 batch). `unknown` exists to prevent silent assumptions during surveys and discovery.

---

## Classification states

### `canonical`

**Meaning:** This artifact IS the source of truth for its domain. Tools, modules, and humans should consume from it. Direct alternatives are violations.

**Examples:**
- `data/org_hierarchy_config.json` (role taxonomy authoritative source)
- `utils/role_taxonomy.py` (canonical RBAC interface)
- `utils/auth_jwt.py` (canonical JWT mint/decode)

**Invariants:**
- Has an authoritative-source declaration in `CANONICAL_TRUTH_REGISTRY.md`
- Has at least one enforcement gate
- Has a named owner
- Documentation (in this artifact or `.md` companion) describes its contract

**Promotion:** Comes from `transitional` (after grace period and gate compliance) or rarely is born `canonical` (when introduced as a constitutional artifact from day one, like this registry itself).

**Demotion:** Goes to `deprecated` only when explicitly retired with a migration path. A `canonical` artifact cannot become `unknown`.

---

### `derived`

**Meaning:** This artifact is a computed view, projection, or cache of one or more `canonical` sources. Its content is determined entirely by its sources; it has no independent authority.

**Examples:**
- `frontend/web/src/index.css` shadcn HSL variables (derived from `frontend/web/src/lib/tokens.ts` hex values)
- `data/audit_log.json` (derived runtime log; the emitter `_audit()` is canonical, the file is its sink)
- Cached computed BSC scores

**Invariants:**
- Has a `derived_from` declaration pointing at one or more `canonical` sources
- Has a derivation mechanism (build script, runtime computation, materialized view) declared
- Stale-detection mechanism exists (timestamp, hash, version, audit gate)
- May be rebuilt from sources at any time without loss of information

**Promotion to `canonical`:** Not generally possible. A derived artifact that gains independent authority must be redesigned with a new authoritative source.

**Demotion to `deprecated`:** When its sources change in ways the derivation cannot capture, or when its existence is no longer justified.

---

### `transitional`

**Meaning:** This artifact is in flight. It exists today and is used today, but is being actively replaced, refactored, or harmonized. Its rules may be temporarily relaxed during the transition window.

**Examples:**
- `utils/auth.py` (Streamlit-era page-access; will be reconciled with React `AuthProvider` in Wave 2)
- v1 admin endpoints currently gated only by `confirm: bool = False` (will gain explicit `require_admin` or `require_role` in Wave 2)
- Streamlit `pages/*.py` (will progressively migrate to React post v10.500)
- `data/users.json` password fields (SHA-256 → bcrypt migration in flight)

**Invariants:**
- Has a declared `transition_target` (the state it's moving toward)
- Has a declared `transition_deadline` or `transition_trigger` (when/why it leaves the transitional state)
- Has a `migration_required: true` flag visible in metadata
- Enforcement gates apply at reduced severity (HIGH or MEDIUM, not CRITICAL) during the window

**Promotion to `canonical`:** When the transition completes and the gate at full severity passes.

**Demotion to `deprecated`:** When the transition target is a replacement and the original artifact is retired.

---

### `deprecated`

**Meaning:** This artifact existed, served a purpose, and is no longer the source of truth. It may still exist on disk for legacy compatibility or audit-trail purposes, but tools and modules should not write to it, and reading from it requires explicit justification.

**Examples (none currently in the system; this is what the state is for):**
- Old Streamlit pages after their React replacements ship and are certified
- Pre-v10.330 retail chain definitions (replaced by `_v10330_canonical_retail_chain`)
- SHA-256 password records after bcrypt migration completes per user

**Invariants:**
- Has a `superseded_by` pointer to the replacement (`canonical` or `transitional`)
- Has a `deprecated_in_version` and `removal_planned_in_version` (or `permanent_archive`)
- New code that depends on it must declare `# DEPRECATED-DEP: <issue>` with tracking

**Promotion:** Cannot return to `canonical` without explicit unretirement (rare; if it happens, it's a constitutional event).

**Demotion to removal:** When the `removal_planned_in_version` arrives, the artifact is removed from disk and its entry moves to a historical-archive section of this registry.

---

### `unknown`

**Meaning:** This artifact has been discovered (e.g. found in `utils_inventory.txt`) but its role, classification, and authority have not yet been determined. **`unknown` is a survey state, never a destination.**

**Examples (during Stage A):**
- `utils/agents/`, `utils/arena/`, `utils/cert/`, `utils/chaos/`, `utils/channels/`, `utils/ml/`, `utils/scenarios/`, `utils/sim/`, `utils/uncertainty/` — directories whose contents were not surveyed in Wave 1

**Invariants:**
- Has a `discovered_in` reference (which survey wave found it)
- Has a `resolution_target_wave` (which subsequent batch will classify it)
- Cannot remain `unknown` longer than 1 batch (per G5)

**Resolution:** Must transition to one of `canonical`, `derived`, `transitional`, or `deprecated` within the resolution window.

---

## Composite classifications

For complex artifacts where a single state is insufficient, the registry supports compound declarations:

### `canonical_with_transitional_subareas`

The parent artifact is `canonical`, but one or more sub-fields, sub-functions, or sub-rules are themselves in `transitional` states.

**Example:**
- `utils/api.py` is `canonical` for API surface
- BUT v1 admin endpoint RBAC enforcement is `transitional` (gated by `confirm:` not by `require_admin`)

**Encoding:** `classification: "canonical_with_transitional_subareas"` + `transitional_subareas: ["..."]`

### `transitional_toward_canonical`

The artifact is `transitional`, and the transition target is `canonical`. Most common compound.

### `transitional_toward_deprecated`

The artifact is `transitional` because it is being retired. Use this rather than `deprecated` until the retirement actually completes.

---

## State transition matrix

| From → To | `canonical` | `derived` | `transitional` | `deprecated` | `unknown` |
|---|---|---|---|---|---|
| **`canonical`** | — | — (rare: a canonical becomes derived if rebuilt as computed view) | OK (refactor) | OK (retire) | ✗ never |
| **`derived`** | ✗ (must be redesigned) | — | OK (rebuild from new source) | OK (retire) | ✗ |
| **`transitional`** | OK (complete) | OK (after refactor) | — | OK (abandon transition) | ✗ |
| **`deprecated`** | ✗ (unretirement is a constitutional event) | ✗ | ✗ | — | ✗ |
| **`unknown`** | OK (after survey) | OK | OK | OK | — (cannot remain) |

Transitions marked `OK` require:
1. Update to `CANONICAL_TRUTH_REGISTRY.md` + `.json`
2. Audit gate adjustment (severity, scope, or both)
3. Entry in `REVIVAL_LEDGER.md` with date and rationale

Transitions marked `✗` require constitutional amendment (separate governance batch).

---

## Enforcement tier taxonomy

Audit gates surface violations at four severity bands. Per Joshua's C5 confirmation: fail-fast for `CRITICAL`, grace-window-then-fail for `HIGH`, tolerable-during-harmonization for `MEDIUM` and `LOW`.

### `CRITICAL`

**Meaning:** A violation that compromises system integrity, security, or canonical truth. **Fails immediately**, blocks certification, blocks deployment.

**Examples:**
- Any `canonical` artifact violating its declared contract
- Authentication or authorization bypass (V-001 family)
- Hardcoded secrets in code (V-009 family)
- Password not bcrypt-hashed on new account (V-003 family)
- A canonical role string used outside `utils/role_taxonomy.py` resolution path
- `data/org_hierarchy_config.json` failing schema validation
- Audit gate self-test failing
- `CANONICAL_TRUTH_REGISTRY.md` pointer broken (file moved/deleted)

**Behavior:** Audit gate returns `passed: false`; verifier fails; certification blocked; CI/CD pipeline aborts. **No grace period.** No "warning today, fail next batch."

---

### `HIGH`

**Meaning:** A violation that should not exist long-term but may be permitted during a declared harmonization window. **Fails after the grace deadline.**

**Examples:**
- A `transitional` artifact violating its target contract after the transition deadline
- An untyped or partially-typed `require_role` call (currently takes raw strings; canonical contract is via `role_taxonomy`)
- A new code path that bypasses an existing `canonical` interface even if formally permitted
- Coverage thresholds dropping below the floor declared in `gate_coverage_thresholds`
- Performance API latency above the threshold in `gate_performance_api_latency`

**Behavior:** During grace window, gate reports as `passed: true` with `warning: "approaching deadline"`. After grace window deadline, gate behaves as `CRITICAL`.

**Grace window default:** 3 batches from the date the violation is first detected and classified `HIGH`. Configurable per-gate.

---

### `MEDIUM`

**Meaning:** A violation that indicates drift, technical debt, or governance gap, but is tolerable during the current harmonization phase. Surfaces in reports; does not block.

**Examples:**
- Documentation inconsistency between code and `.md` artifact
- A `canonical` artifact missing its owner field
- Test coverage in a single module below the per-module target but above the floor
- A `transitional` artifact past 50% of its grace window with no progress signal
- Stale backup files past retention policy

**Behavior:** Reported in audit summary; flagged for owner attention; does not block certification.

**Escalation:** If `MEDIUM` violations persist across 5+ consecutive batches without remediation, the gate may auto-escalate to `HIGH`.

---

### `LOW`

**Meaning:** A finding worth visibility — drift candidates, optimization opportunities, style violations — that does not impact integrity or operational readiness. Informational only.

**Examples:**
- Comment-style inconsistencies
- Non-canonical module file naming conventions
- Optimization opportunities flagged by static analysis
- `unknown` artifacts that haven't been resolved within their target wave but are not blocking

**Behavior:** Listed in audit report under "advisories" section; does not block any pipeline. May be cleared per-batch by the owner.

---

## Severity assignment rules

When a gate detects a violation, severity is determined by:

1. **Lookup in the gate's `severity_map`** if declared (most precise)
2. **Match against the violation type's default** in this registry's `default_severity_per_violation_type` table
3. **Fallback:** `MEDIUM`

Gates SHOULD declare `severity_map` explicitly. The fallback exists to prevent gates without explicit declaration from silently treating violations as `LOW`.

### Default severity table

| Violation type | Default severity |
|---|---|
| Authentication bypass | `CRITICAL` |
| Authorization missing on state-changing route | `CRITICAL` |
| Hardcoded secret | `CRITICAL` |
| Password not bcrypt | `CRITICAL` |
| Canonical artifact pointer broken | `CRITICAL` |
| Canonical interface bypassed (e.g. raw role string match outside `role_taxonomy`) | `HIGH` |
| Transitional artifact past grace deadline | `HIGH` (escalates to CRITICAL) |
| Coverage threshold dropped | `HIGH` |
| Performance threshold exceeded | `HIGH` |
| Documentation inconsistency | `MEDIUM` |
| Missing owner field | `MEDIUM` |
| Style violation | `LOW` |
| `unknown` artifact past resolution window | `MEDIUM` |

---

## Rollout tolerance windows

Per Joshua's C5 (categorized rollout visibility), Stage C audit gates support these windows. When a new constitutional rule is introduced (e.g. "no descriptive role string outside `role_taxonomy`"), it ships in a phased manner:

### Phase 1 — Visibility (1-2 batches)

Gate is registered, runs in CI, but violations are reported at `LOW` severity regardless of their inherent severity. Owners see the scope of drift. No blocking.

### Phase 2 — Grace (next 3-5 batches)

Severity escalates to the inherent default. Owners must remediate or document an explicit exception. Blocking applies only at `CRITICAL`.

### Phase 3 — Full enforcement (after grace)

Severity is final. `CRITICAL` and `HIGH` block. No more soft transitions.

### Permanent exemptions

If a violation cannot be remediated (e.g. third-party library forces a pattern that violates a rule), an explicit `# noqa: <gate_name>` or registry-level exemption is required. Exemptions must include rationale and review date. `gate_canonical_truth_registry_sync` verifies exemption metadata.

---

## How this registry is consumed

### By `CANONICAL_TRUTH_REGISTRY.md` (Wave 1)

Each domain has a `classification` field that must be one of the five states. Composite classifications use the `_with_transitional_subareas` suffix or `transitional_toward_*` form.

### By Stage C audit gates

When a gate detects a violation:
1. It looks up the artifact's classification in `CANONICAL_TRUTH_REGISTRY.json`
2. It looks up the severity for the violation type in this registry
3. It looks up the current rollout phase for the gate itself
4. It computes the effective severity (intrinsic × current phase)
5. It emits the gate result with that severity

### By future AI sessions

Reading this registry tells the session:
- What classification states exist
- What severity bands exist
- How to interpret a violation in audit output
- When a transitional state's grace window expires
- What an "unknown" classification means (work to resolve it, not work to ignore it)

---

## Open registry items

Items needing explicit classification in subsequent waves:

1. **All Wave 5 specialty domains** (AI governance, resilience) — currently `canonical` placeholders in `CANONICAL_TRUTH_REGISTRY.md`; need their canonical-interface contracts surveyed to confirm.

2. **Streamlit page-access RBAC** (`utils/auth.py`) — currently `transitional` with proposed transition target of `deprecated` post v10.500. Wave 2 RBAC_MATRIX will confirm the timeline.

3. **53 v1 admin endpoints** — currently grouped as `transitional` sub-area of api.py canonical. Wave 2 API_CONTRACTS will classify each individually.

4. **`utils/agents/`, `arena/`, `cert/`, `chaos/`, `channels/`, `ml/`, `scenarios/`, `sim/`, `uncertainty/` subdirectories** — currently `unknown`. Wave 3 ORGANS_REGISTRY will resolve.

5. **CHANGELOG governance state** — `docs/CHANGELOG_*.md` and `docs/releases/*.md` are empty. Wave 6 CHANGELOG_MASTER will establish the seed state and declare the canonical format.

---

**End of GOVERNANCE_CLASSIFICATION_REGISTRY.md**
