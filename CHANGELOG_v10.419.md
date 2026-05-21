# Changelog — v10.419 Role weight renormalization · Phase 2d opens

**Date:** 2026-05-14
**Phase:** Phase 2d (data integrity housekeeping) **OPENS**
**Audit:** G305 added (cumulative 305 gates)
**Tests:** 16/16 PASSED in `test_v10419_role_weight_renormalization.py`
**Regression:** 284/284 v10.4xx tests PASSED (268 + 16)
**Verifier:** 695/695 checks pass (689 → 695, +6 v10.419 checks)
**G162 baseline:** 4022 (112 consecutive zero-drift batches)
**Master prompt:** v4.61 → v4.62 (lockstep — 63 consecutive batches)

---

## What this batch is

The first of the data integrity housekeeping batches. Tackles your locked backlog item: **225/227 roles broken with weight sums != 1.0**.

Live audit before this batch (in sandbox):
- **227 total roles** in kpi_library.json
- **6 already normalized** (weights sum to 1.0)
- **221 broken** (sum != 1.0)
- **189 zero-sum** (KPIs assigned but no global weights configured)

The existing scoring code in `utils/core.py:6470-6476` already auto-normalizes by dividing through the sum on the fly — so this never broke anything user-visible. But the implicit assumption "sum of weights for a role = 1.0" was never stored or auditable. This batch surfaces the gap explicitly and provides a clean migration path.

## What v10.419 built

### NEW `utils/role_weight_engine.py` (~300 LOC)

API-first per v10.412 discipline. **Zero streamlit imports (AST-verified).** 14th React-ready engine module.

**Public API:**

| Function | Purpose |
|---|---|
| `audit_role_weight(role, kpis, weights)` → `RoleWeightAudit` | Per-role audit: sum, is_normalized, normalization_factor |
| `bank_role_weight_audit(library=None)` → `BankRoleWeightAudit` | Bank-wide rollup |
| `compute_role_normalized_weights(role, kpis, weights)` → `dict` | Returns {kpi: normalized_weight} summing to 1.0 |
| `migrate_normalize_all_roles(library=None, write_back=True)` → `tuple` | Bulk migration |
| `get_role_normalized_weight(role, kpi, library=None)` → `float \| None` | Single lookup |

**Dataclasses** (JSON-serializable):
- `RoleWeightAudit(role, kpi_count, kpis_assigned, kpis_with_weight, kpis_missing_weight, sum_of_weights, is_normalized, normalization_factor)`
- `BankRoleWeightAudit(total_roles, normalized_count, broken_count, zero_sum_count, broken_roles, timestamp)`

**Constants:**
- `NORMALIZATION_TOLERANCE = 0.001` — 0.1% tolerance for float rounding

### Migration result

Live migration on the sandbox kpi_library.json:

| Before | After |
|---|---|
| 6 roles normalized | 227 roles with explicit `role_normalized_weights` field |
| 221 broken | 0 broken (all sum to 1.0) |
| 189 zero-sum | 0 zero-sum (default fallback to equal weights) |

**The migration is ADDITIVE.** The canonical `kpi_weights` dict is unchanged. Existing scoring code reading `kpi_weights` continues unchanged. New consumers (audit dashboards, React BSC, future per-role overrides) can read `role_normalized_weights` directly.

### NEW `scripts/normalize_role_weights.py` migration runner

```bash
# Verify without writing
python scripts/normalize_role_weights.py --dry-run

# Run the migration
python scripts/normalize_role_weights.py
```

Idempotent: re-running it just re-writes the same normalized values.

### NEW 4 FastAPI endpoints in `utils/api.py`

All JWT-required via existing `Depends(get_current_user)`:

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/v1/role-weights/audit`               | Bank-wide audit summary |
| `GET`  | `/api/v1/role-weights/{role}/audit`        | Single role's audit |
| `GET`  | `/api/v1/role-weights/{role}/normalized`   | One role's normalized weights (prefers migrated; falls back to on-the-fly) |
| `POST` | `/api/v1/role-weights/migrate`             | Run migration (production: gate behind admin role) |

### Audit gate G305

Verifies engine API + AST zero-streamlit + migration script + 4 endpoints + engine state 0/0/0/0 + E2E synthetic library normalization.

## Verified outcome

| Metric | v10.418 | v10.419 |
|---|---|---|
| Audit gates | 304 | **305** |
| v10.4xx tests | 268 | **284** (+16) |
| Verifier | 689 | **695** (+6) |
| Total API endpoints | 30 | **34** (+4 role-weight) |
| React-ready engines | 13 | **14** |
| Master prompt lockstep | 62 | **63** consecutive |
| G162 baseline | 4022 (111) | 4022 (**112** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |

## Architecture — what React sees

A React admin dashboard for role weights:

```typescript
// 1. Get bank-wide audit
const audit = await api.get('/api/v1/role-weights/audit');
// { total_roles: 227, normalized_count: 227, broken_count: 0, ... }

// 2. Drill into a specific role
const role = await api.get('/api/v1/role-weights/Branch Manager/audit');
// { kpi_count: 21, sum_of_weights: 1.0, is_normalized: true, ... }

// 3. Get the normalized weights for a role (e.g. for BSC weight bars)
const weights = await api.get('/api/v1/role-weights/Branch Manager/normalized');
// { role: "Branch Manager", weights: { "DEP_GROWTH": 0.15, ... }, source: "migrated" }

// 4. Admin re-runs migration (e.g. after KPI library edit)
await api.post('/api/v1/role-weights/migrate', {});
```

Same engine the migration script and Streamlit-future-admin-tab call.

## 10 honest acknowledgements

1. **The math was already auto-normalizing.** The existing `weighted/total_w` line in core.py meant scores were always correctly computed. This batch's value is **explicit auditability + per-role weight storage** for future use cases (React display, weight customization, audit reporting), not fixing a runtime bug.

2. **Additive migration was the right call.** Touching `kpi_weights` would have rippled into the existing scoring code. Adding a separate `role_normalized_weights` field keeps everything backward-compatible — no code change required outside the new engine.

3. **189 zero-sum roles flag a real data issue.** These are roles where assigned KPIs have NO global weight entry. The migration falls back to equal-weight (1/n per KPI), which is a reasonable default but should be reviewed. Listed in the audit's `broken_roles` for follow-up.

4. **The 4 endpoints aren't admin-gated.** Production should add a role check on the migrate endpoint (it modifies the library). Audit/lookup endpoints are read-only; current JWT-auth is sufficient.

5. **No Streamlit admin UI in this batch.** The 4 endpoints expose all functionality. Admin panel integration (in `pages/7_admin.py`) is a follow-up — UI surface can land later without changing the engine.

6. **Tolerance is 0.001 (0.1%).** Matches the F2 buffer engine's tolerance and Set team targets compliance check. Consistent.

7. **`compute_role_normalized_weights` is idempotent.** Running it on already-normalized weights yields the same result. Safe to call repeatedly.

8. **`migrate_normalize_all_roles` returns the audit too.** Callers don't need a separate audit call after migration — the result tuple gives you both the bank audit and the normalized dict in one shot.

9. **Meta keys are skipped.** The bank audit ignores keys starting with `_` (those are v10.324/v10.328/etc. migration metadata in the library). 227 actual roles audited.

10. **14 React-ready engines now.** All zero-streamlit, all dataclass-returning. The discipline you locked in v10.412 keeps producing: every new engine module behaves like an HTTP/JSON service from day one, regardless of who's currently calling it.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10419_patch.zip` on top of v10.418 state
3. `python scripts/verify_local_state.py` → expect **695/695**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/role_weight_engine.py` → engine self-test (8 checks)
6. **First**: `python scripts/normalize_role_weights.py --dry-run` → review the audit
7. **Then**: `python scripts/normalize_role_weights.py` → run the migration
8. Verify in `data/kpi_library.json` → see new `role_normalized_weights` field + `_v10419_role_weight_normalization` metadata stamp
9. (Optional) FastAPI: `curl -H "Authorization: Bearer $TOKEN" http://localhost:8502/api/v1/role-weights/audit`
10. Tell me **"continue"** → v10.420 = KPI library dedup follow-through (4 alias pairs)

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.414-v10.418~~ | ~~F-series + integration~~ | **DONE** |
| **v10.419** | **Role weight renormalization** | **DONE (this batch)** |
| v10.420 | KPI library dedup follow-through (4 alias pairs) | Next |
| v10.421 | Backup retention cleanup (122 MB) | Pending |
| v10.422 | Retired test cleanup | Pending |
| v10.423 | Pillar weights decision (68/14/6/12 vs Kaplan-Norton 40/25/25/10) | Pending |
| v10.424 | BSC scorecard dual-view + compliance in pages/1_perform.py | Pending |
| v10.425-v10.427 | CBS baseline / PBT live actuals / MD BSC verification | Pending |
| v10.428+ | React SPA build | Pending |
