# Changelog — v10.416 F3: per-line-manager retain authorization

**Date:** 2026-05-14
**Phase:** Phase 2c (architectural features) — F3
**Audit:** G302 added (cumulative 302 gates)
**Tests:** 18/18 PASSED in `test_v10416_retain_authorization.py`
**Regression:** 239/239 v10.4xx tests PASSED (221 + 18)
**Verifier:** 676/676 checks pass (666 → 676, +10 v10.416 checks)
**G162 baseline:** 4022 (109 consecutive zero-drift batches)
**Master prompt:** v4.58 → v4.59 (lockstep — 60 consecutive batches)

---

## What this batch is

Lands your F3 architectural concern. Per your design: 100% cascade required up to Branch Manager tier; below BM, the line manager's immediate boss ticks "can retain" per direct report.

The **authorization surface** is complete this batch — boss can grant/revoke retention per direct report, audit trail is full, both manager-side and staff-side UIs are wired, FastAPI endpoints exposed.

The **enforcement surgery** (relaxing the implicit 100% cascade rule when retention is granted) is deferred — the existing Set team targets save logic has 5+ paths and that change deserves its own batch. F3 surface ships now; enforcement integration comes after this surface is exercised.

## What v10.416 built

### NEW `utils/cascade_retain_engine.py` (~280 LOC)

API-first per v10.412 discipline. **ZERO streamlit imports (AST-verified).**

**Tier rule** (`TIER1_ROLE_KEYWORDS`):

| Keyword | Examples | Eligibility |
|---|---|---|
| Managing Director, Chief Executive | MD himself | Tier 1 — must cascade 100% |
| Director | Director Retail Banking, Director Commercial Banking | Tier 1 |
| Head Of, Head of | Head of Retail, Head of MSME, Head of Corporates | Tier 1 |
| Regional Head | All regional heads | Tier 1 |
| Branch Manager | All 35 BMs | Tier 1 |
| Chief variants | Chief Retail, Chief Commercial, Chief Financial, etc. | Tier 1 |
| Everything else | BOM (94 staff), SR RM SME, RM Corporate, etc. | **Below BM → eligible** |

**Public API:**

| Function | Returns | Purpose |
|---|---|---|
| `is_eligible_for_retention(role)` | `bool` | True iff role NOT in tier 1 |
| `set_retain_authorization(staff_code, authorized_by, period, can_retain=True, note='')` | `RetainAuthorization` or `None` | Boss grants/revokes |
| `get_retain_authorization(staff_code, period)` | `RetainAuthorization` or `None` | Single lookup |
| `is_retention_allowed(staff_code, period)` | `bool` | Convenience — auth exists AND can_retain=True |
| `get_team_retain_authorizations(direct_report_codes, period)` | `list[RetainAuthorization]` | Boss-side rollup |
| `remove_retain_authorization(staff_code, period, removed_by)` | `bool` | Revoke |
| `retention_audit_summary(period)` | `RetentionAuditSummary` | Bank-wide rollup |

**Dataclasses** (all JSON-serializable):

- `RetainAuthorization(staff_code, period, authorized_by, authorized_at, can_retain, note)`
- `RetentionAuditSummary(period, total_authorizations, granted_count, revoked_count, authorizing_managers)`

**Persistence:** `data/retain_authorizations.json` (dict keyed by `{staff_code}|{period}`).

### Set team targets — NEW `🎯 Step 4 (optional) · F3 Retain authorizations` expander

Sits after the F2 stretch tuner. Shown only if the manager has at least one eligible direct report (the engine filters by `is_eligible_for_retention(role)`).

Contents:
- **Summary metrics**: Eligible reports count, retention granted count, not configured count
- **Per-report rows**: Name + role (left), can_retain checkbox + note (middle), Save button (right)
- **Status indicator** under each row: "Retention GRANTED by X on date" or "REVOKED" or "Not configured — defaults to 100% cascade required"

Logs `RETAIN_AUTH_SET` audit events with payload `{staff_code}|{period}|granted|revoked`.

### My targets — NEW retention badge

When a staff member opens their My targets sub-tab, they see a clear status callout if any authorization exists for their staff_code in the current period:

- **Green** "✓ Retention authorized for {period}" — granted by boss, with note if any
- **Red** "📝 Retention explicitly revoked for {period}" — revoked by boss

This removes ambiguity: staff knows whether they're bound to 100% cascade or have discretion.

### NEW 4 FastAPI endpoints

Cascade router now has **26 routes** (was 22). All JWT-required:

| Method | Path | Purpose |
|---|---|---|
| `GET`    | `/api/v1/cascade/retain/{staff_code}/{period}`  | Get auth (404 if none) |
| `PUT`    | `/api/v1/cascade/retain/{staff_code}/{period}`  | Boss sets/updates |
| `DELETE` | `/api/v1/cascade/retain/{staff_code}/{period}`  | Revoke |
| `GET`    | `/api/v1/cascade/retain/summary/{period}`       | Bank-wide rollup |

**Pydantic models:** `RetainAuthResponse`, `RetainAuthSetRequest`, `RetentionAuditSummaryResponse`.

### Audit gate G302

Verifies engine surface + tier rule + zero streamlit + data persistence + Set team targets UI + My targets badge + endpoints registered + Pydantic models + engine state 0/0/0/0 + E2E set/get/eligibility/revoke cycle.

## What's deferred

**Cascade-validation surgery** — modifying the existing Set team targets save logic so that allocations from a staff with retention auth can sum to less than `total_target` (with the difference becoming the retained portion). This requires touching the 5+ save paths in cascade.py and re-deriving the "allocated_sum" semantics. Better as its own focused batch after the F3 surface is exercised.

The engine ships `is_retention_allowed(staff_code, period)` for that future batch to consume — single source of truth, no parallel logic needed.

## Verified outcome

| Metric | v10.415 | v10.416 |
|---|---|---|
| Audit gates | 301 | **302** |
| v10.4xx tests | 221 | **239** (+18) |
| Verifier | 666 | **676** (+10) |
| Cascade endpoints | 22 | **26** (+4 retain) |
| React-ready cascade engines | 11 | **12** |
| Master prompt lockstep | 59 | **60** consecutive |
| G162 baseline | 4022 (108) | 4022 (**109** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |
| React-readiness | 84% | **86%** |

## Architecture — what React sees

A React component for the boss's retention dashboard:

```typescript
// 1. Get the manager's direct reports (from cascade rollup)
const team = await api.get(`/api/v1/cascade/rollup/${myCode}/2026`);

// 2. For each report, check if they have an existing authorization
const auths = await Promise.all(
  team.directReports.map(r =>
    api.get(`/api/v1/cascade/retain/${r.staff_code}/2026`)
       .catch(() => null)  // 404 if not configured
  )
);

// 3. Boss toggles a checkbox → grant authorization
await api.put(`/api/v1/cascade/retain/${staffCode}/2026`, {
  can_retain: true,
  note: 'Branch lead — local discretion'
});

// 4. Bank-wide oversight (CFO/risk audit view)
const summary = await api.get('/api/v1/cascade/retain/summary/2026');
// → { total_authorizations, granted_count, revoked_count, authorizing_managers }
```

Same engine the Streamlit UI calls.

## 10 honest acknowledgements

1. **Tier rule is keyword-based**, not enum-driven. `is_eligible_for_retention("Branch Manager")` matches via `"Branch Manager"` keyword. Works for the current org structure; if titles drift, the keyword list updates.

2. **No new role-level enforcement yet.** Setting an authorization doesn't change cascade validation today. It's signal data — surfaced in My targets, queryable via API, audit-trailed. The actual save-time relaxation is the next surgical batch.

3. **`is_retention_allowed` is the integration point.** When the cascade-validation surgery happens, the save logic will call this and skip the "must total 100%" check when True. Single source of truth.

4. **Both grant and revoke are explicit.** `can_retain=False` records an explicit denial — surfaces in My targets as a red callout. Distinct from "not configured" (no auth exists at all). Useful for boss documentation: "I considered it and said no."

5. **The 94 BOM tier is the realistic audience.** Branch Operations Managers are the most likely retention candidates (they run branches, often have a few CSO/teller reports). SME/Corporate RMs are eligible but typically have flat structures and may not need retention.

6. **`get_team_retain_authorizations` takes a list of codes**, not a manager_code. This keeps the engine free of CascadeManager dependency. The Streamlit page passes its own direct-report list.

7. **The audit summary is bank-wide.** For a CFO or risk auditor wanting to know "across the whole bank for 2026, how many people did managers authorize to retain?" — one call to `retention_audit_summary("2026")` returns the answer.

8. **Pydantic models are the React contract.** When the React team consumes the OpenAPI spec, the TypeScript types for retention auth will be auto-generated. No drift between backend and frontend.

9. **F-series is nearly done.** F2 (buffer cap + per-allocation stretch) v10.414+v10.415. F3 (retain auth surface) v10.416. F5 (dual-view BSC display) is the final F-series concern. v10.417 wraps it up. The cascade architecture stops being a moving target after that.

10. **Engine count: 12 React-ready cascade engines.** All zero-streamlit, all dataclass-returning, all 26 endpoints behind a single JWT-guarded prefix. The discipline you locked in v10.412 keeps paying.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10416_patch.zip` on top of v10.415 state
3. `python scripts/verify_local_state.py` → expect **676/676**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/cascade_retain_engine.py` → engine self-test (12 checks)
6. Launch Streamlit → log in as a Branch Manager (or any manager with BOM reports)
7. Target Cascade → Cascade & allocate → Set team targets → scroll to bottom → see `🎯 Step 4 (optional) · F3 Retain authorizations` expander
8. Tick "Can retain" for one BOM, add a note, click Save → see status indicator update
9. Log out, log in as that BOM, go to Target Cascade → My view → My targets → see the green retention badge
10. (Optional) Start FastAPI → `http://localhost:8502/api/docs` → see 4 new `/retain/*` endpoints
11. Tell me **"continue"** → v10.417 = F5 dual-view BSC (primary=stretch, secondary=base aside)

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.414~~ | ~~F2 part A: Buffer engine + MD cap~~ | **DONE** |
| ~~v10.415~~ | ~~F2 part B: Per-allocation stretch tuner~~ | **DONE** |
| **v10.416** | **F3: Per-line-manager retain authorization** | **DONE (this batch)** |
| v10.417 | F5: Dual-view BSC (primary=stretch, secondary=base aside) | Next |
| v10.418 | Cascade-validation surgery (relax 100% rule for authorized reports) | After |
| v10.419 | Role weight renormalization (225/227 broken) | Pending |
| v10.420 | KPI library dedup follow-through | Pending |
| v10.421 | Backup retention cleanup | Pending |
| v10.422 | Retired test cleanup | Pending |
| v10.423 | Pillar weights decision | Pending |
| v10.424-v10.426 | CBS baseline / PBT live actuals / MD BSC verification | Pending |
| v10.427+ | React SPA build | Pending |
