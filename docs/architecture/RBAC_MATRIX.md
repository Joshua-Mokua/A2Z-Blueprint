# A2Z Blueprint MIS 360 — RBAC Matrix

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md` + `ROLE_GOVERNANCE.md`)
**Status:** `canonical` (with `transitional` sub-areas — see Section 8)
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 2)
**Last updated:** 2026-05-22
**Owner:** Security / Platform + Admin
**Machine-readable equivalent:** `RBAC_MATRIX.json`
**Companion artifact:** `API_CONTRACTS.md` (per-endpoint RBAC mapping)

---

## Purpose

This document defines **who can do what** in the A2Z system. It maps roles (resolved via `utils/role_taxonomy.py`) to capabilities. It is the source of truth for:

- Every `require_role([...])` call in `utils/api.py` and routers
- Every `require_module_access(...)` call in Streamlit pages (after OI-1 rename)
- Every conditional rendering decision in React (Phase 2 v10.497)
- Every audit gate that verifies authorization is in place

This matrix does **not** specify HOW authorization is checked. That's `auth_jwt.py` (FastAPI) and `auth.py` (Streamlit). This matrix specifies the **vocabulary**: the permission names, their owning capabilities, and the role/tier mappings.

---

## Doctrine

**RB1 — Capabilities are named, not anonymous.** Every authorization decision references a named capability (e.g. `bsc:read_all_staff`, `cascade:harmonize`, `users:summary`). Anonymous role checks (`if user.role == "MD"`) are violations of R2.

**RB2 — Capabilities map to tiers, not strings.** The canonical mapping is from capability → set of `RoleClassification` predicates (tier, scope, SBU). Role-string lists are an implementation convenience but the conceptual model is tier-based.

**RB3 — Deny by default.** A capability not explicitly granted is denied. There is no "allow all roles" — even MD-only capabilities are named and listed.

**RB4 — Two stages: authenticate, then authorize.** Authentication is `Depends(get_current_user)` (any logged-in user). Authorization is `Depends(require_role(...))` or equivalent capability check. They are separate concerns.

**RB5 — Destructive operations require RBAC, not just `confirm=true`.** Endpoints that mutate persistent state must require an explicit role/tier, not rely solely on a `confirm: bool = False` query parameter. The `confirm` parameter is an additional safety measure, not the authorization mechanism. (This is a Wave 2 finding; current state is `transitional`.)

---

## Permission vocabulary

Permissions are named `<domain>:<verb>` where:
- `<domain>` is a system area (auth, bsc, cascade, pipeline, credit, aml, users, dashboard, cache, integration, role-weights, hr, etc.)
- `<verb>` is the action (read, read_all, read_own, write, migrate, repair, archive, etc.)

Where the action is qualified, we use `<domain>:<verb>_<qualifier>` (e.g. `bsc:read_staff` vs `bsc:read_all_staff`).

---

## Capability ↔ tier matrix

The matrix below grants capabilities by profitability tier and/or seniority tier. A user's role is classified via `utils/role_taxonomy.classify_role()`; the user has the capability if their classification matches any of the tier predicates in the granted set.

**Notation:**
- `MD` = seniority tier 0 (Chief Executive & Managing Director)
- `C-suite` = seniority tier 1 (Chiefs + Directors)
- `Head` = seniority tier 2 (Head Of, Regional Head)
- `Sr Mgr` = seniority tier 3 (Senior Manager, Area Manager)
- `Mgr` = seniority tier 4 (Manager, Branch Manager)
- `Officer` = seniority tier 5
- `Entry` = seniority tier 6
- `structural_owner`, `portfolio_owner`, etc. = profitability tier (orthogonal)
- `[ALL_AUTHENTICATED]` = any logged-in user
- `[ADMIN]` = `is_admin=True` flag in users.json (separate from role)

### Auth domain

| Capability | Grant | Notes |
|---|---|---|
| `auth:login` | `[PUBLIC]` | Unauthenticated by design (`/api/auth/login`) |
| `auth:me` | `[ALL_AUTHENTICATED]` | Read own user record (`/api/auth/me`) |
| `auth:logout` | `[ALL_AUTHENTICATED]` | Revoke own token (`/api/auth/logout`) |

### Dashboard / read-only summaries

| Capability | Grant | Notes |
|---|---|---|
| `bsc:read_own` | `[ALL_AUTHENTICATED]` | Read own BSC scorecard |
| `bsc:read_subordinates` | `Mgr`+ when target is subordinate per `hierarchy_synth` | Manager reads direct reports' BSC |
| `bsc:read_all_staff` | `Head`+ when target in scope | Head of X reads all in their SBU |
| `bsc:read_summary` | `[ALL_AUTHENTICATED]` | Aggregate BSC summary (`/api/bsc/summary`) |
| `pipeline:read_summary` | `[ALL_AUTHENTICATED]` | Pipeline summary (`/api/pipeline/summary`) |
| `pipeline:read_own_deals` | `[ALL_AUTHENTICATED]` filtered by ownership | Own deals only |
| `pipeline:read_all_deals` | `MD` + `C-suite` + `Head` of relevant SBU | Unrestricted deal access |
| `credit:read_summary` | `[ALL_AUTHENTICATED]` | Credit summary (filtered) |
| `credit:read_watchlist` | `Mgr`+ in Credit SBU OR `Head`+ structural | Watchlist visibility |
| `aml:read_summary` | `[ALL_AUTHENTICATED]` | AML summary (filtered) |
| `aml:read_all` | Roles in Compliance SBU OR `MD` + Chief Risk + Chief Compliance + Chief Internal Auditor | Full AML visibility |
| `users:read_summary` | `[ALL_AUTHENTICATED]` | User directory (no sensitive data) |
| `dashboard:md` | `MD` only | MD cockpit (`/api/dashboard/md`) |

### Cache & system

| Capability | Grant | Notes |
|---|---|---|
| `cache:read_stats` | `[ALL_AUTHENTICATED]` | Cache stats (`/api/cache/stats`) |
| `cache:clear` | `[ADMIN]` | Cache invalidation (`/api/cache/clear`) |
| `vitals:read` | `[ALL_AUTHENTICATED]` | System vitals (`/api/v1/vitals/*`) |

### Integration / actuals

| Capability | Grant | Notes |
|---|---|---|
| `integration:read_rules` | `[ALL_AUTHENTICATED]` | Read aggregation rules |
| `integration:read_actuals` | `[ALL_AUTHENTICATED]` filtered by scope | Period actuals |
| `integration:read_metrics` | `[ALL_AUTHENTICATED]` | Resolution metrics |
| `integration:run_period` | `[ADMIN]` OR `MD` + `Chief Financial Officer` + `Chief Risk Officer` | **CURRENTLY TRANSITIONAL — only confirm=true gating** |
| `integration:read_coverage` | `[ALL_AUTHENTICATED]` | Coverage stats |
| `integration:read_rule_explain` | `[ALL_AUTHENTICATED]` | Per-KPI rule explanation |

### v1 admin governance (audit + migrate)

| Capability | Grant (target) | Current state |
|---|---|---|
| `role-weights:audit` | `[ALL_AUTHENTICATED]` | OK |
| `role-weights:migrate` | `[ADMIN]` | **TRANSITIONAL — currently only confirm gate** |
| `kpi-dedup:audit` | `[ALL_AUTHENTICATED]` | OK |
| `kpi-dedup:migrate` | `[ADMIN]` | **TRANSITIONAL** |
| `backup-retention:audit` | `[ADMIN]` | Currently `[ALL_AUTHENTICATED]` — should be ADMIN |
| `backup-retention:apply` | `[ADMIN]` | **TRANSITIONAL — destructive, currently only confirm gate** |
| `test-cleanup:audit` | `[ADMIN]` | Should be ADMIN |
| `test-cleanup:archive` | `[ADMIN]` | **TRANSITIONAL** |
| `bsc-audit:full` | `[ALL_AUTHENTICATED]` filtered | OK for read |
| `bsc-audit:*` (6 sub-endpoints) | `[ALL_AUTHENTICATED]` | OK for read |
| `bsc-pillar:audit` | `[ALL_AUTHENTICATED]` | OK |
| `bsc-pillar:migrate` | `[ADMIN]` | **TRANSITIONAL** |
| `bsc-library:audit` | `[ALL_AUTHENTICATED]` | OK |
| `bsc-library:register` | `[ADMIN]` | **TRANSITIONAL** |
| `bsc-completeness:audit` | `[ALL_AUTHENTICATED]` | OK |
| `bsc-completeness:repair` | `[ADMIN]` | **TRANSITIONAL** |
| `bsc-weights:audit` | `[ALL_AUTHENTICATED]` | OK |
| `bsc-weights:renormalize` | `[ADMIN]` | **TRANSITIONAL** |
| `bsc-codes:audit` | `[ALL_AUTHENTICATED]` | OK |
| `bsc-codes:fix` | `[ADMIN]` | **TRANSITIONAL** |
| `admin-validation:library` | `[ADMIN]` | Should be ADMIN |
| `admin-validation:legacy-aliases` | `[ADMIN]` | **TRANSITIONAL** |
| `cascade-360:audit` | `[ALL_AUTHENTICATED]` | OK |
| `cascade-360:stage` | `[ALL_AUTHENTICATED]` | OK |
| `harmonize:all` | `[ADMIN]` | **TRANSITIONAL** |
| `harmonize:stage` | `[ADMIN]` | **TRANSITIONAL** |

### HR & people management

| Capability | Grant | Notes |
|---|---|---|
| `onboarding:audit` | `Head`+ in HR SBU OR `[ADMIN]` | Bank-wide |
| `onboarding:audit_staff` | Manager of subordinate OR `Head`+ in HR SBU | Per-staff |
| `onboarding:simulate` | `[ADMIN]` | **CRITICAL: VERIFY AUTH STATE — see OI-7** |
| `exit-risk:audit` | `Head`+ in HR SBU OR `[ADMIN]` | Bank-wide |
| `exit-risk:audit_staff` | Manager of subordinate OR `Head`+ | Per-staff |
| `exit-risk:simulate_staff` | Manager of subordinate OR `Head`+ in HR SBU | Per-staff simulation |
| `hr-audit:full` | `Head`+ in HR SBU OR `[ADMIN]` | Full HR health |
| `hr-audit:dimension` | `Head`+ in HR SBU | Per-dimension |
| `peer-learning:cards` | `[ALL_AUTHENTICATED]` filtered to own or subordinates | Per-staff cards |
| `peer-learning:generate_cards` | `[ADMIN]` | **CRITICAL: VERIFY AUTH STATE — see OI-7** |
| `peer-learning:match_skill` | `[ALL_AUTHENTICATED]` | Find peers ahead |
| `coaching:script` | Manager of staff_code OR `Head`+ | Coaching scripts |
| `predict:achievement` | `[ALL_AUTHENTICATED]` filtered to own or subordinates | EOM prediction |
| `gamification:badges` | `[ALL_AUTHENTICATED]` filtered | Own / subordinates |
| `gamification:evaluate` | Manager of subordinate OR `[ADMIN]` | Triggers evaluation |
| `gamification:leaderboard` | `[ALL_AUTHENTICATED]` filtered to relevant scope | Leaderboard |
| `efficiency:read` | `[ALL_AUTHENTICATED]` filtered to own or subordinates | Per-KPI |
| `wellness:read` | Manager of subordinate OR `[ADMIN]` (subject's own access permitted) | Burnout assessment |
| `wellness:alerts` | Manager only (`manager_code` matches user) | Manager's reports |

### HR actuals (read-only computed)

| Capability | Grant | Notes |
|---|---|---|
| `hr-actuals:staff` | `[ALL_AUTHENTICATED]` filtered to own or subordinates | Per-staff HR KPIs |
| `hr-actuals:bank_wide` | `Head`+ in HR SBU OR `[ADMIN]` | Bank-wide HR KPI |
| `hr-actuals:coverage` | `[ALL_AUTHENTICATED]` | Coverage stats |

### Streamlit page access (legacy, transitional)

These are the modules historically gated by `utils/auth.py::require_access` (and its `require_role` alias). After OI-1 rename, they will be gated by `require_module_access`. The capability names mirror the module names used in `users.json::accessible_modules`.

| Page module | Default grant | Notes |
|---|---|---|
| `bsc` | `[ALL_AUTHENTICATED]` filtered | Own BSC |
| `pipeline` | `[ALL_AUTHENTICATED]` filtered | Own deals |
| `cascade` | `Mgr`+ | Cascade view |
| `admin` | `[ADMIN]` | Admin panel |
| `cbs` | `Head`+ in Finance/Operations OR `[ADMIN]` | CBS explorer |
| `kpi_library` | `[ALL_AUTHENTICATED]` (read) / `[ADMIN]` (write) | KPI library |
| `target_cascade` | `Mgr`+ (set targets for subordinates) / `[ADMIN]` (set bank targets) | Target cascade |
| `users` | `[ADMIN]` | User management |

(Full Streamlit page list — 158 pages per Master Prompt v5.40 — to be enumerated in Wave 3 ORGANS_REGISTRY.)

---

## Scope-bounded capabilities

Some capabilities are scoped — a user may have the capability *for some subset of records* but not others. The scope is determined by hierarchy or SBU classification.

### "Own" scope

A user can access their own records. Determined by username/staff_code match.

- `bsc:read_own`, `pipeline:read_own_deals`, `efficiency:read` (own), etc.

### "Subordinates" scope

A user (typically `Mgr`+) can access records of their direct/transitive reports. Determined by `utils/hierarchy_synth.py` walking the reporting tree.

- `bsc:read_subordinates`, `gamification:evaluate`, `wellness:alerts` (for manager's reports), `coaching:script`, etc.

### "SBU" scope

A user can access records for staff/customers within their SBU classification. Determined by `utils/role_taxonomy.get_sbu(role)`.

- `bsc:read_all_staff` (filtered to user's SBU when not MD/C-suite)
- `pipeline:read_all_deals` (filtered to user's SBU when not MD/C-suite)
- `aml:read_all` (Compliance SBU only)

### "National" scope

Unrestricted access. Reserved for `MD`, `C-suite`, and specifically-granted `Head` roles when the SBU itself spans the bank (e.g. Head of Risk).

- `dashboard:md` (MD only)
- `aml:read_all` (also granted to Chief Risk, Chief Compliance, Chief Internal Auditor)

---

## The `is_admin` flag and its relationship to roles

`data/users.json` has two fields that affect authorization:

- `is_admin: bool` — granted by Admin; carries broad system access including all `[ADMIN]` capabilities
- `is_ict_admin: bool` — IT/system administration; broader still in some operational contexts

These flags are **orthogonal to role classification**. A user can be:
- Admin without being MD or in C-suite (e.g. an IT administrator)
- MD without `is_admin=True` (the MD's role classification grants MD capabilities; `is_admin` is for system administration on top)

The system's `require_admin` Depends checks `is_admin` OR (in Streamlit) `is_admin OR is_ict_admin`.

The `users.json` schema also supports:
- `accessible_modules: list[str]` — explicit module access grants (Streamlit)
- `hidden_modules: list[str]` — explicit module access denials (Streamlit)
- `can_view_all: bool` — broad read scope (Streamlit)

These three fields are consumed by `utils/auth.py::has_access`. After the OI-1 rename, they continue to be consumed by `require_module_access`. They are `transitional` — the React migration will consolidate them into the canonical capability model.

---

## Currently transitional sub-areas

These RBAC declarations document the **target state** for Wave 2. The **current state** has known gaps that are tracked here and remediated in Stage C.

### Gap A: 53 v1 admin endpoints declare only `Depends(get_current_user)`

**Current state:** Every `/api/v1/*` endpoint uses `Depends(get_current_user)` regardless of operation type. Destructive endpoints (those that write to disk, modify users.json, run migrations) rely on a `confirm: bool = False` query parameter as the safety mechanism.

**Target state:** Endpoints in the "TRANSITIONAL" rows above should add `Depends(require_admin)` (using the existing `auth_jwt.require_admin`) as an additional check **before** the `confirm` gate. The `confirm` parameter remains as a UX safety, but RBAC is the authorization.

**Migration plan:**

1. **Stage C audit gate** — `gate_v1_admin_endpoints_have_rbac`: scan `utils/api.py` for `@app.post("/api/v1/*/migrate"|*/apply|*/archive|*/repair|*/renormalize|*/fix|*/register|*/legacy-aliases|*/run-period|*/simulate|*/generate-cards|*/harmonize/*"` and verify each declares `Depends(require_admin)` or `Depends(require_role([...]))`. Initial severity `HIGH` with 3-batch grace window per `GOVERNANCE_CLASSIFICATION_REGISTRY.md`.

2. **Implementation batch** — touch the route signatures to add the auth Depends. Order: backup-retention/apply first (most destructive), then harmonize/all, then bsc-*/migrate variants.

3. **Verification** — re-run G12 + new gate; confirm zero violations.

### Gap B: OI-7 — Two v1 routes with unclear auth state

`POST /api/v1/onboarding/simulate` and `POST /api/v1/peer-learning/generate-cards` extracted with this signature:

```python
def onboarding_simulate_endpoint(
    payload: Dict[str, Any] = Body(...)
)
```

The signature ends at the closing paren of `Body(...)`. **This is almost certainly an extraction artifact** — the regex used to dump `v1_route_signatures.txt` captured up to the first `)` it found, which closes `Body(...)`. The actual signature in `utils/api.py` likely continues with `, user: dict = Depends(get_current_user)` on the next line.

**Verification command** (run from project root):

```
findstr /n "def onboarding_simulate_endpoint\|def peer_learning_generate_endpoint" utils\api.py
```

Then view the surrounding ~10 lines of `utils/api.py` to confirm the full signature. If `Depends(get_current_user)` IS present, this is closed (extraction artifact). If NOT present, this is a **CRITICAL** G12 violation requiring immediate fix.

**Tracked as OI-7** until verified.

### Gap C: Backup-retention/audit and test-cleanup/audit return data without filtering

These two read endpoints are marked `[ALL_AUTHENTICATED]` above but expose information that could be operationally sensitive (backup directory sizes, retention metadata). Recommend upgrading to `[ADMIN]` for the read variant as well as the apply/archive variants.

**Tracked for Stage C.**

---

## Hierarchy-aware scope enforcement (manager → subordinates)

Several capabilities are scoped to "manager of subordinate." The implementation requires the auth layer to know the hierarchy. Today this is done in route handlers by calling `ReportingLineManager` (in `utils/core.py`). The canonical contract:

```python
from utils.core import ReportingLineManager

def is_manager_of(manager_user: dict, subordinate_staff_code: str) -> bool:
    """Returns True if manager_user reports above subordinate_staff_code in the canonical hierarchy."""
    rlm = ReportingLineManager()  # singleton or session-scoped
    chain = rlm.get_chain_to_root(subordinate_staff_code)
    return manager_user.get("staff_code") in chain
```

Stage C will introduce a `require_manager_of(target_staff_code_path_param)` Depends factory that wraps this logic.

---

## React Phase 2 — `useRole()` hook contract

(Forward-looking; full specification in `FRONTEND_GOVERNANCE.md` Wave 4.)

The React app will consume role data via a single hook:

```typescript
import { useRole } from '@/lib/role';

const role = useRole();
// role.tier               — profitability tier
// role.seniorityTier      — seniority tier (0-6)
// role.sbu                — SBU
// role.branchScope        — scope
// role.capabilities       — array of granted capability names
// role.isAdmin            — boolean
// role.hasCapability(cap) — function
```

The hook hydrates from a single API call `GET /api/roles/me` which calls `utils/role_taxonomy.classify_role()` server-side and returns the structured classification plus the resolved capability list.

**Critical contract:** React conditional rendering uses `role.hasCapability("...")`, NEVER direct string comparison like `if (user.role === "MD")`.

---

## Open items

| ID | Title | Resolution wave |
|---|---|---|
| OI-2 | 53 v1 admin endpoints classification (this matrix) | Implementation in next governance batch |
| OI-7 | Verify auth state of `/onboarding/simulate` + `/peer-learning/generate-cards` | Immediate (Joshua verifies via grep) |
| OI-9 | `/api/roles/me` endpoint contract | Wave 4 FRONTEND_GOVERNANCE |
| OI-10 | `require_role` factory extension with `tier=`, `sbu=`, `seniority_max=` | Stage C |
| OI-11 | `require_manager_of` Depends factory | Stage C |
| OI-12 | `gate_v1_admin_endpoints_have_rbac` audit gate | Stage C |
| OI-13 | Streamlit page list enumeration with per-page RBAC | Wave 3 ORGANS_REGISTRY |

---

**End of RBAC_MATRIX.md**
