# A2Z Blueprint MIS 360 — Role Governance

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md`)
**Status:** `canonical`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 2)
**Last updated:** 2026-05-22
**Owner:** Admin / HR Operations
**Authoritative source:** `data/org_hierarchy_config.json`
**Canonical interface:** `utils/role_taxonomy.py`
**Machine-readable equivalent:** `ROLE_GOVERNANCE.json`
**Enforcement gate:** `G260 gate_role_taxonomy_alignment` (scripts/audit.py:36381)

---

## Purpose

This document is the **human-readable canonical reference** for every role-related decision the system makes. Every authorization check, every BSC assignment, every cascade computation, every report filter that depends on role identity must conform to what's documented here. Where this document and the code disagree, the code wins (the audit gate enforces); this document is then corrected in the next governance batch.

The authority for role data is `data/org_hierarchy_config.json`. The authority for role logic is `utils/role_taxonomy.py`. This document documents what those two artifacts say.

---

## Doctrine

**R1 — Two orthogonal axes.** Every role is classified on (a) seniority and (b) profitability. Neither axis determines the other. A role with the same seniority can have different profitability classifications.

**R2 — Canonical resolution only.** Role logic decisions go through `utils/role_taxonomy.py`. Hardcoded role strings in route bodies, page logic, or React conditional rendering are violations.

**R3 — Display vs logic.** Raw role strings appear in (a) `utils/role_taxonomy.py` itself, (b) UI display layers after canonical resolution has already occurred. Nowhere else.

**R4 — Joshua-authored batches are constitutional.** The five canonical batches recorded in `org_hierarchy_config.json` are load-bearing decisions, not historical curiosities. Reverting any requires an explicit governance batch with full rationale.

**R5 — `users.json` and `hr.json` are the data; `org_hierarchy_config.json` is the schema.** Every role string appearing in user or staff records must classify via the taxonomy. `validate_role_coverage()` enforces this.

---

## The two axes

### Seniority axis (`role_tiers`)

7 tiers from MD root down to entry-level frontline. Defined in `org_hierarchy_config.json::role_tiers` with 143 explicit role-to-tier mappings + 8 keyword-fallback groups.

| Tier | Meaning | Example roles |
|---|---|---|
| 0 | MD root (only one allowed) | Chief Executive & Managing Director, Managing Director |
| 1 | C-suite + Directors | Chief Retail Banking Officer, Chief Risk Officer, Director Retail Banking, Director Commercial Banking, General Manager - Bancassurance |
| 2 | Head Of / Regional Head | Head of Branches, Head of Treasury, Head Of Corporates & Trade Finance, Regional Head |
| 3 | Senior Manager / Area Manager | Area Manager, Senior Manager Direct Sales Force, Senior Manager Treasury |
| 4 | Manager / Branch Manager | Branch Manager, Senior Branch Manager, Branch Operations Manager, Credit Manager |
| 5 | Officer / Specialist / RM | Relationship Manager - SME, Credit Analyst, Treasury Dealer, Senior Relationship Manager - Corporate Banking |
| 6 | Teller / CSO / DSR / Trainee | Teller, Customer Service Officer, Direct Sales Representative |

**Keyword fallback** (when a role doesn't match an explicit mapping):

| Tier | Keywords (first match wins, lower tier first) |
|---|---|
| 0 | "managing director", "chief executive" |
| 1 | "chief ", "general manager", "director " |
| 2 | "head of", "head ", "regional head" |
| 3 | "senior manager", "area manager", "senior branch", "senior relationship manager" |
| 4 | "manager" |
| 5 | "officer", "specialist", "analyst", "supervisor", "engineer", "administrator", "dealer", "developer", "representative" |
| 6 | "teller", "junior ", "trainee", "assistant", "clerk" |

### Profitability axis (`profitability_axis.tiers`)

5 categories representing the directness of bank impact. Defined in `org_hierarchy_config.json::profitability_axis` (shipped v10.374, enforced by G260).

| Tier | Meaning | Tagging permitted? |
|---|---|---|
| `portfolio_owner` | Tagged to customers; drives sales; Σ(customer PBT) attributed to them | **Yes** — appears in `accounts.csv::relationship_manager_code` |
| `proposition_owner` | Drives overlapping proposition (Women Banking, Diaspora, Agribusiness) | **No** — overlaps customer portfolios; attribution via overlap views |
| `structural_owner` | Owns PBT at structural level (branch, region, SBU, bank) via rollup | **No** — owns aggregated PBT, not direct customer relationships |
| `service` | Branch operational role; occasionally tagged when introducing accounts | **Yes** — secondary tagging only |
| `support` | Head office function (Risk, Compliance, IT, HR, Finance, Audit, Legal) | **No** — owns cost center / function, not direct PBT |

**Taggability invariant** (R6, enforced by G260 check 6):

> Only `portfolio_owner` and `service` roles may appear in `accounts.csv::relationship_manager_code` or `customers.csv::rm_code`. `proposition_owner`, `structural_owner`, and `support` roles MUST NOT tag.

### Branch scope (`profitability_axis.branch_scopes`)

3 values declaring where a role physically/organizationally sits:

| Scope | Meaning |
|---|---|
| `branch_bound` | Works at one specific branch |
| `head_office` | Works at HO; portfolio may span multiple branches |
| `national` | Bank-wide responsibility |

### Strategic Business Unit (SBU)

7 SBU values aligned with `data/segment_sbu_mapping.json`:

```
Retail Banking, Commercial Banking, Corporate Banking, Treasury,
Digital_Agency, Support, Executive
```

Customer-facing SBUs are subset of `segment_sbu_mapping`. Operational/support SBUs (`Support`, `Executive`, `Treasury`, `Digital_Agency`) are axis-level and not customer-facing.

---

## The canonical interface — `utils/role_taxonomy.py`

This is the **only** legitimate way to make role-based decisions.

### Module purity contract

- Zero upward imports
- Reads only `data/org_hierarchy_config.json` (schema) and `data/users.json` + `data/hr.json` (for coverage audit)
- Safe to call from any layer (engines, transports, gates)
- No Streamlit, no FastAPI, no transport-specific dependencies

### Exported constants

```python
# Profitability tier values
TIER_PORTFOLIO_OWNER   = "portfolio_owner"
TIER_PROPOSITION_OWNER = "proposition_owner"
TIER_STRUCTURAL_OWNER  = "structural_owner"
TIER_SERVICE           = "service"
TIER_SUPPORT           = "support"

ALL_TIERS = (TIER_PORTFOLIO_OWNER, TIER_PROPOSITION_OWNER,
             TIER_STRUCTURAL_OWNER, TIER_SERVICE, TIER_SUPPORT)

# Branch scope values
SCOPE_BRANCH_BOUND = "branch_bound"
SCOPE_HEAD_OFFICE  = "head_office"
SCOPE_NATIONAL     = "national"

ALL_SCOPES = (SCOPE_BRANCH_BOUND, SCOPE_HEAD_OFFICE, SCOPE_NATIONAL)

# SBU values
SBU_RETAIL     = "Retail Banking"
SBU_COMMERCIAL = "Commercial Banking"
SBU_CORPORATE  = "Corporate Banking"
SBU_TREASURY   = "Treasury"
SBU_DIGITAL    = "Digital_Agency"
SBU_SUPPORT    = "Support"
SBU_EXECUTIVE  = "Executive"

ALL_SBUS = (SBU_RETAIL, SBU_COMMERCIAL, SBU_CORPORATE, SBU_TREASURY,
            SBU_DIGITAL, SBU_SUPPORT, SBU_EXECUTIVE)
```

### Exported dataclass

```python
@dataclass(frozen=True)
class RoleClassification:
    role: str                # the original role string
    tier: str                # one of ALL_TIERS (profitability)
    branch_scope: str        # one of ALL_SCOPES
    sbu: str                 # one of ALL_SBUS
    matched_via: str         # 'explicit' or 'keyword_fallback:<keyword>' or 'no_match_default'
```

### Exported functions

| Function | Returns | Use case |
|---|---|---|
| `classify_role(role)` | `RoleClassification` | Full classification when you need all attributes |
| `get_profitability_tier(role)` | `str` | Just the profitability tier |
| `get_branch_scope(role)` | `str` | Just the branch scope |
| `get_sbu(role)` | `str` | Just the SBU |
| `can_be_tagged(role)` | `bool` | **The single authority on tagging** |
| `list_all_classified_roles()` | `list[str]` | All roles with explicit classification |
| `list_roles_by_tier(tier)` | `list[str]` | All explicit roles in a tier |
| `list_roles_by_sbu(sbu)` | `list[str]` | All explicit roles in an SBU |
| `validate_role_coverage()` | `dict` | Audit: every role in users.json + hr.json classifies |
| `self_test()` | `None` (asserts) | Module self-verification (12 tests) |

### Coverage validation output shape

```python
{
    "total_used": int,        # distinct roles in users + hr
    "explicit": int,           # in role_classification map
    "keyword": int,            # matched via keyword fallback
    "default": int,            # fell to no_match_default (REVIEW)
    "unclassified": list[str], # sorted list of default cases
    "by_tier": {tier: count}   # distribution
}
```

`G260` requires `default == 0` for the gate to pass.

---

## Org hierarchy invariants

Declared in `org_hierarchy_config.json::_validation_rules`:

| Invariant | Meaning | Enforced by |
|---|---|---|
| `exactly_one_root_required` | One and only one MD | `gate_hierarchy_synth` |
| `no_cycles_allowed` | Reporting graph is a tree | `gate_hierarchy_classification_correct` |
| `only_chiefs_report_to_md` | Depth-1 from root is C-suite only | `gate_canonical_retail_chain`, `_v10399_joshua_corrections` |
| `every_staff_has_a_chain_to_root` | No orphans | `gate_hierarchy_synth` |
| `default_max_span_of_control: 15` | Soft span limit | warnings only |
| `default_max_chain_depth: 12` | Maximum nesting depth | warnings only |

The synthesizer (`utils/hierarchy_synth.py`) consumes `org_hierarchy_config.json::role_manager_whitelist` (131 entries) to validate that each subordinate role's parent comes from the allowed-manager set. Violations from `hr.json` source data are flagged and replaced with synthesis-derived linkages.

---

## The Chief roster

10 Chief roles + 1 MD = 11 top-level positions. Each Chief has a synthetic staff code for hierarchy synthesis when no real staff occupies the role.

| Role | Synthetic staff code | Primary department |
|---|---|---|
| Chief Executive & Managing Director | (real: `william001` / 300001) | Executive |
| Chief Retail Banking Officer | `EXEC-CRO-001` | Retail Banking |
| Chief Credit Officer | `EXEC-CCO-001` | Credit |
| Chief Operating Officer | `EXEC-COO-001` | Operations |
| Chief Financial Officer | `EXEC-CFO-001` | Finance |
| Chief Information Officer | `EXEC-CIO-001` | IT & Digital |
| Chief Risk Officer | `EXEC-CRSO-001` | Risk & Compliance |
| Chief Compliance Officer | `EXEC-CCMP-001` | Legal |
| Chief Internal Auditor | `EXEC-CIA-001` | Internal Audit |
| Chief Human Resource Officer | `EXEC-CHRO-001` | People & HR |
| Chief Commercial Officer | `EXEC-CCMO-001` | Commercial & Corporate |
| General Manager - Bancassurance | (real or synthetic; tier 1) | Bancassurance |

Synthetic MD (`EXEC-MD-001`) was **deleted in `_v10399_joshua_corrections`**. The real MD `william001` (William Mwanake) is the sole tier-0 occupant.

23 departments → owning Chief mapping in `department_chief_mapping`. Departments without a real Chief get the synthetic record injected by the hierarchy synthesizer.

---

## Joshua-authored canonical batches (constitutional load-bearing decisions)

These are recorded in `org_hierarchy_config.json` as explicit blocks. Reverting any requires an explicit governance batch.

### `_v10330_canonical_retail_chain` (v10.330)

**Decision:** Retail reporting chain locked at:

```
Branch Manager → Area Manager → Head of Branches → Chief Retail Banking Officer
```

**Specific changes:**
- TIGHTENED `role_manager_whitelist`: `Branch Manager` parents reduced from `[Area Manager, Senior Branch Manager, Head of Branches]` to `[Area Manager]` only
- TIGHTENED `role_manager_whitelist`: `Senior Branch Manager` parents reduced from `[Area Manager, Head of Branches]` to `[Area Manager]` only
- ALIGNED `utils/hierarchy_synth.py`: SBMs treated as PEERS of standard BMs (both report to Area Manager), not as a supervisory tier

**Rationale:** Per banking convention articulated by Joshua: Branch performance = Branch Manager's performance, Area Manager BSC = aggregate of branches reporting to them, Head of Branches BSC = aggregate of Area Managers, Chief Retail BSC = aggregate of Head of Branches. Senior BMs run flagship branches but don't supervise other BMs.

### `_v10396_joshua_clarification` (2026-05-13)

**Decision:** Branch structure clarified:

- Branch tops are **Branch Manager (regular)** or **Senior Branch Manager (big branches)**
- BOM, BRM, BSRO, RO PB, RO BB, DSR all report to BM/SBM
- BOS, Teller, CSO report to BOM
- Senior Branch Manager tier corrected from 3 → 4 (branch-level, not regional)
- DSR reporting line moved from BOS/BOM to BM/SBM

### `_v10398_joshua_hq_canonical` (2026-05-13)

**Decision:** Every HQ role mapped to a Chief. 103 roles added, 9 updated, 127 tier updates.

**Chief-to-domain mapping:**

| Chief | Domains |
|---|---|
| CFO | Finance + Business Analytics + Treasury |
| CRO (Risk) | Risk + Compliance + Chief Compliance Officer |
| CIO | IT + DFS (later updated by `_v10399`) |
| COO | Operations + Marketing + Procurement + CX + Trade Operations |
| CHRO | HR |
| CRBO | Branches + Women Banking + Diaspora + RM Diaspora + Business Development (DSR) |
| CCO (Commercial) | Corporates + SME + GIB + RMs |
| Chief Credit Officer | Credit Analysis + Admin + Monitoring + Collections |
| Chief Internal Auditor | Audit roles |
| Chief Legal (= Chief Compliance Officer in updated taxonomy) | Legal roles |
| GM Bancassurance | Manager Underwriting + HQ Bancassurance |

**Bancassurance dotted-line rule:** Bancassurance Officers at branches report to Branch Manager primary with dotted line to GM Bancassurance.

**Specific ordering fixes:**
- SDCO branches → BM/SBM primary (94 branch SDCOs found)
- RM Corporate Banking → SRM Corporate primary
- RM Agribusiness → SRM SME primary
- Credit Analyst → distributed under analysis managers

### `_v10399_joshua_corrections` (2026-05-13)

**Decision:** 7-point corrections to v10.398:

1. Synthetic Managing Director deleted from users.json (only Chief Executive & Managing Director / William Mwanake remains)
2. Head of Digital Financial Services moved from CIO → CCO (DFS is commercially-led; DCOs at branches have dotted reporting line to Head of DFS)
3. Manager Card Operations remains under DFS (now via CCO)
4. Corporate Sales Dealer confirmed under Treasury (CFO)
5. Trade Finance Back Office Manager confirmed under Head of Operations → COO
6. Trade Finance split confirmed (relationships → CCO, operations → COO)
7. Admin role moved from CHRO to MD (this is the developer/MD-login admin account)

### `_v10469_role_kpis_resolution` (v10.469, in `data/kpi_library.json`)

**Decision:** All 1,469 role-KPI short-code references in `kpi_library.json::role_kpis` resolved to canonical library KPI IDs.

```json
{
  "_resolved": 1469,
  "_unresolved": 0
}
```

This locks the link between role taxonomy (this document) and KPI library. Every role classified by `role_taxonomy.classify_role()` has a deterministic canonical KPI list via `kpi_library.json::role_kpis[role]`.

---

## Resolution of OI-1 — `require_role` name collision

### The problem

Two functions named `require_role` exist in the system today with incompatible signatures:

**`utils/auth.py::require_role`** (Streamlit-era):
```python
require_role = require_access  # module-level alias

def require_access(module: str, user: Optional[Dict[str, Any]] = None) -> bool:
    # Streamlit page gate; returns True if access granted
```

**`utils/auth_jwt.py::require_role`** (v10.497 P1.1):
```python
def require_role(roles: list[str]) -> Callable:
    """FastAPI Depends factory."""
    def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(403)
        return user
    return _checker
```

**Constitutional violation:** Same name, incompatible signatures, different semantics, different return types. Pure name collision. Imports from one accidentally resolving to the other would produce silent failures or incorrect authorization.

### The resolution

**Rename `utils/auth.py::require_role` → `utils/auth.py::require_module_access`.**

The Streamlit function is the one that gets renamed because:

1. Its actual semantics ("require access to a named module/page") are better captured by `require_module_access`
2. The name `require_role` accurately describes the FastAPI factory (it takes role names and returns a dependency)
3. The Streamlit version is `transitional` (per `CANONICAL_TRUTH_REGISTRY.md`) — it will eventually be deprecated when Streamlit pages migrate to React
4. The FastAPI version is the canonical new contract going forward

### Migration steps (to be executed in a follow-up commit on `feature/governance-constitution`)

1. In `utils/auth.py`:
   - Rename internal alias: `require_role = require_access` → `require_module_access = require_access`
   - Update `__all__` to remove `require_role` and add `require_module_access`
   - Add a deprecation shim that warns when `require_role` is imported (one batch grace period before removal):

```python
def require_role(*args, **kwargs):
    """DEPRECATED: use require_module_access for Streamlit page gates,
    or import from utils.auth_jwt for FastAPI route gating.

    Removed in next governance batch.
    """
    import warnings
    warnings.warn(
        "utils.auth.require_role is deprecated and ambiguous with "
        "utils.auth_jwt.require_role. Use require_module_access for "
        "Streamlit pages or utils.auth_jwt.require_role for FastAPI routes.",
        DeprecationWarning, stacklevel=2,
    )
    return require_access(*args, **kwargs)
```

2. In every `pages/*.py` that uses `require_role`:
   - Update import: `from utils.auth import require_role` → `from utils.auth import require_module_access`
   - Update call sites: `require_role("module_name")` → `require_module_access("module_name")`

3. In Stage C, add a new audit gate:

```python
def gate_no_require_role_collision() -> Dict[str, Any]:
    """Verify utils/auth.py does not export require_role; only require_module_access."""
    # Implementation: parse utils/auth.py, check __all__, check no module-level require_role
```

### Severity classification

- **Before rename:** `HIGH` (transitional collision; flagged at warning during grace window)
- **After rename:** `CRITICAL` if reintroduced (any `utils/auth.py::require_role` reappearance is constitutional rot)

### Timeline

- **Wave 2 (this batch):** Declared resolution path; gate placeholder in Stage C
- **Next governance batch:** Execute the rename + import updates + gate activation
- **One batch after:** Remove deprecation shim

---

## Role coverage state (snapshot)

From `validate_role_coverage()` running against the current `users.json` + `hr.json`:

**Note: these counts are derived from the survey context (1,439 users, 124 distinct roles). The actual `validate_role_coverage()` result must be re-run to populate this section authoritatively. In the next batch, Stage C gate output should be captured here.**

Expected shape:
- `total_used`: ~124 distinct roles
- `explicit`: ≥30 (G260 minimum threshold)
- `keyword`: remainder
- `default`: 0 (G260 hard requirement)
- `unclassified`: empty list

If `default > 0`, the offending roles must be added to `role_classification` or `tier_keyword_fallback` in `org_hierarchy_config.json` before G260 will pass.

---

## Consumer contract — how other modules use this

### Authorization checks (FastAPI)

```python
from fastapi import Depends
from utils.auth_jwt import require_role
from utils.role_taxonomy import classify_role, TIER_STRUCTURAL_OWNER

# Pattern A — string-list (current v10.497 P1.1)
@app.get("/api/admin-thing", dependencies=[Depends(require_role(["Chief Executive & Managing Director", "Chief Retail Banking Officer"]))])
def admin_thing():
    ...

# Pattern B — canonical-tier (recommended for Stage C; require_role extension)
@app.get("/api/structural-thing", dependencies=[Depends(require_role(tier=TIER_STRUCTURAL_OWNER))])
def structural_thing():
    ...

# Pattern C — manual classification inside handler
@app.get("/api/something")
def something(user: dict = Depends(get_current_user)):
    classification = classify_role(user.get("role", ""))
    if classification.sbu != "Retail Banking":
        raise HTTPException(403)
    ...
```

### BSC / cascade computations (engines)

```python
from utils.role_taxonomy import classify_role, can_be_tagged, TIER_PORTFOLIO_OWNER

def attribute_pbt_to_rm(account):
    rm_role = lookup_role(account.rm_code)
    if not can_be_tagged(rm_role):
        # Constitutional violation in the source data
        raise InvariantError(f"Account tagged with non-taggable role: {rm_role}")
    # ...
```

### React conditional rendering (Phase 2 v10.497)

```typescript
// FUTURE — to be specified in FRONTEND_GOVERNANCE.md (Wave 4)
import { useRole } from '@/lib/role';

function AdminPanel() {
  const role = useRole();
  if (role.tier !== 'structural_owner') return null;
  // ...
}
```

The `useRole()` hook (Phase 2 v10.497) consumes classification data from a `/api/roles/me` endpoint (to be added), which calls into `utils/role_taxonomy.classify_role()` server-side and returns the structured result. The React layer never sees raw role strings for logic decisions.

---

## Permitted exceptions

The following are **the only** places where raw role strings legitimately appear:

1. Inside `utils/role_taxonomy.py` itself (canonical implementation)
2. Inside `data/org_hierarchy_config.json` (canonical data)
3. Inside `data/users.json` and `data/hr.json` (user records)
4. Inside `scripts/audit.py` (gate implementations testing the taxonomy)
5. In UI display layers after classification has happened (e.g. `{user.role}` in a JSX greeting)
6. In role-keyed dictionaries like `role_kpis`, `role_default_targets.json`, `role_skill_matrix.json` (canonical data keyed by role name)

Anywhere else — route handlers, page logic, business engines, React effects, computation functions — raw role strings are violations.

---

## Open items carried to subsequent waves

| ID | Title | Resolution wave |
|---|---|---|
| OI-1 (this artifact) | `require_role` name collision — resolution path declared; execution next batch | Next governance batch after Wave 6 |
| OI-8 | Capture live `validate_role_coverage()` output in this document | Next Wave 2 amendment |
| OI-9 | Define `/api/roles/me` endpoint contract for React useRole() hook | Wave 4 FRONTEND_GOVERNANCE |
| OI-10 | Extend `require_role` factory to accept `tier=`, `sbu=`, `seniority_max=` filters | Stage C |

---

**End of ROLE_GOVERNANCE.md**
