# React Frontend Readiness Audit — v10.412

**Date:** 2026-05-14
**Per Joshua:** "We are setting everything in place to ensure seamless REACT front end which is the requirement."

This document audits the cascade module's readiness for a React SPA frontend and codifies the API-first pattern for v10.412+ batches.

---

## Architecture target

```
┌─────────────────────────┐         ┌─────────────────────────┐
│   React SPA             │  HTTPS  │   FastAPI backend       │
│   (production UI)       │ ◄─────► │   (utils/api.py)        │
│                         │  JSON   │                         │
└─────────────────────────┘         └─────────────────────────┘
                                              ▲
                                              │ calls
                                              ▼
                                    ┌─────────────────────────┐
                                    │   Engine modules        │
                                    │   (utils/*_engine.py)   │
                                    │   PURE COMPUTATION      │
                                    └─────────────────────────┘
                                              ▲
                                              │ reads
                                              ▼
                                    ┌─────────────────────────┐
                                    │   JSON data layer       │
                                    │   (data/*.json)         │
                                    └─────────────────────────┘
```

Streamlit pages remain the **internal admin/staging tool**. React SPA is the **production employee-facing UI**.

---

## What's ALREADY React-ready

### 1. FastAPI backend exists ✓

- `utils/api.py` defines the main FastAPI app
- 11 existing API router modules (cockpit, compliance, crud, legal, product, treasury, etc.)
- Each `api_*.py` uses `APIRouter()` pattern with JWT-protected endpoints
- Documented endpoint maps (see `utils/api_cockpit.py` header)
- React SPA is the explicit consumer per existing docstrings

### 2. Cascade engines are streamlit-free ✓

All 5 v10.406+ engines are PURE Python with zero Streamlit dependency:
- `utils/manager_rollup.py` (compute_team_rollup)
- `utils/pillar_impact_engine.py` (pillar_breakdown_for_staff)
- `utils/target_scenario_simulator.py` (simulate_alternative)
- `utils/kpi_ownership_pairing.py` (apply_pairing_strategy)
- `utils/cascade_health_engine.py` (bank_health_summary)

All return dataclasses → trivially JSON-serializable via `dataclasses.asdict()`.

### 3. JSON data layer ✓

- `target_cascade.json` — cascade allocations
- `users.json` — staff
- `kpi_library.json` — KPIs + role mappings
- `bsc_actuals_*.json` — actuals per period
- `cascade_review_requests.json` — negotiation
- `kpi_ownership_map.json` — co-KPI pairing
- `capacity_feedback.json` — v10.412 (NEW)

All standard JSON; consumable by React without ORM layer.

### 4. CascadeManager class ✓

- All cascade operations (`set_allocation`, `get_what_i_was_given`, `cascade_coverage`, `request_review`, `resolve_review`, `auto_escalate_overdue_reviews`) are class methods
- Operate on JSON files
- Decoupled from Streamlit session state

### 5. Defensive iteration patterns ✓

Per v10.409 fix, all `cascade.items()` iterations skip meta-keys (`_*` prefix). React API responses won't crash on migration stamps.

---

## What needs to land for full React readiness

### Gap 1: No FastAPI router for cascade module yet

**Status**: Engines exist but no `utils/api_cascade.py` exposes them.

**Required**: New router with endpoints (all JWT-protected, all GET unless mutating):

```
GET  /api/cascade/health/{period}                  → bank_health_summary
GET  /api/cascade/health/pillar/{period}           → health_by_pillar
GET  /api/cascade/health/sbu/{period}              → health_by_sbu
GET  /api/cascade/health/broken-chains/{period}    → broken_chains
GET  /api/cascade/rollup/{manager_code}/{period}   → compute_team_rollup
GET  /api/cascade/pillar/{staff_code}/{period}     → pillar_breakdown_for_staff
GET  /api/cascade/scenario/current/{manager}/{kpi}/{period}  → load_current_scenario
POST /api/cascade/scenario/simulate                → simulate_alternative
GET  /api/cascade/pairing/shared-kpis              → list_shared_kpis
GET  /api/cascade/pairing/co-owners/{kpi}          → get_co_owners
POST /api/cascade/pairing/compute                  → apply_pairing_strategy
GET  /api/cascade/capacity-feedback/{period}       → list_capacity_feedback (v10.412)
POST /api/cascade/capacity-feedback                → submit_capacity_feedback
GET  /api/cascade/reviews/{period}                 → get_review_requests
POST /api/cascade/reviews                          → request_review
POST /api/cascade/reviews/{rr_id}/resolve          → resolve_review
GET  /api/cascade/export/xlsx/{period}             → cascade XLSX
GET  /api/cascade/export/hris/{period}             → HRIS-shape CSV
GET  /api/cascade/export/bonus/{period}            → bonus-calc shape
```

This is **v10.413 (E7 Cascade API & Exports)** scope — was already on the roadmap; React requirement makes it the highest-impact remaining batch.

### Gap 2: JSON serialization helpers

Dataclasses convert via `asdict()` but enum/datetime/Decimal need encoders.

**Required**: Standard `dataclass_to_json(obj)` helper used by every cascade endpoint.

### Gap 3: OpenAPI / type-safe contracts

FastAPI auto-generates OpenAPI from type hints. Need to ensure every endpoint has:
- Pydantic response models OR explicit `response_model=` declarations
- Request body validation via Pydantic
- Generated TypeScript types via `openapi-typescript` (developer workflow)

### Gap 4: CORS configuration

For React on different port/host (dev: localhost:3000 → backend on 8000):
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://a2z.ecobank.co.ke"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Gap 5: Auth — JWT issuance/refresh for React

Existing Streamlit auth uses session state. React SPA needs:
- POST /api/auth/login → JWT
- POST /api/auth/refresh → new JWT
- Bearer header on every request

Likely already in `utils/api.py` since other modules use JWT. Verify in v10.413.

---

## API-first pattern codified

**Every new feature from v10.412 onwards follows this pattern:**

1. **Engine module** (`utils/<feature>_engine.py`):
   - Pure Python, zero Streamlit
   - Dataclass outputs for JSON-serializable returns
   - Functions take primitive types (string, int, list) — no Streamlit session objects
   - Module-level caches keyed by stable IDs (period, staff_code)

2. **Data layer** (`data/<feature>.json`):
   - JSON-Schema-friendly structure
   - Versioned with `_version` / `_note` meta keys (skipped by defensive iteration)

3. **FastAPI router** (`utils/api_<feature>.py`):
   - APIRouter mounted at `/api/cascade/<feature>`
   - JWT-protected per existing pattern
   - Pydantic response models
   - One endpoint per engine function

4. **Streamlit page** (`pages/12_cascade.py` sub-tab):
   - Thin view layer
   - Calls engine functions (same calls React will make via API)
   - No business logic in the page

This ensures **the same engine serves both Streamlit (internal) and React (production)** — zero rework when React frontend lands.

---

## v10.412 (E6 Capacity Feedback) — applying the pattern

Following the codified pattern:

1. **NEW** `utils/capacity_feedback_engine.py`:
   - `submit_feedback(staff_code, period, kpi, constraint_type, constraint_value, rationale)` → `CapacityFeedback`
   - `list_feedback(period, manager_code=None, staff_code=None, kpi=None)` → `list[CapacityFeedback]`
   - `feedback_for_kpi(manager_code, kpi, period)` → list (used by Set team targets)
   - `update_status(feedback_id, status, response, resolved_by)` → CapacityFeedback
   - All return `@dataclass` with `asdict()` serialization

2. **NEW** `data/capacity_feedback.json`:
   ```json
   {
     "_version": "v10.412",
     "_note": "Staff capacity feedback raised BEFORE manager finalizes cascade",
     "feedback": [
       {
         "id": "CF0001",
         "staff_code": "300050",
         "staff_name": "Jane Wanjiru",
         "period": "2026",
         "kpi": "PBT",
         "constraint_type": "team_size",
         "constraint_value": "Only 3 RMs in our branch vs target assumes 6",
         "suggested_target_max": 8000000000,
         "rationale": "Industrial Area branch has lower customer density...",
         "status": "Open",
         "raised_at": "2026-01-15T08:30:00",
         "resolved_at": null,
         "resolved_by": null,
         "response": null
       }
     ]
   }
   ```

3. **STUB** `utils/api_capacity_feedback.py`:
   - `GET /api/cascade/capacity-feedback/{period}` → list
   - `POST /api/cascade/capacity-feedback` → submit
   - `PATCH /api/cascade/capacity-feedback/{id}/status` → resolve

   (Router defined; mounting into main app deferred to v10.413 E7 batch.)

4. **NEW sub-tab** `💬 Capacity feedback` inside Cascade & allocate (visible to all staff):
   - Staff view: raise constraint
   - Manager view: see constraints from team
   - Surfaces in Set team targets when manager allocates a KPI

5. **Surface in Set team targets**: when manager allocates a KPI X to staff Y, if there's open capacity feedback from Y on KPI X, show inline warning.

---

## Status summary

| Layer | Status | Notes |
|---|---|---|
| Data layer (JSON files) | ✅ Ready | Universal consumer |
| Engine modules | ✅ Ready | All 5 v10.406+ engines are pure Python |
| Pure-Python lib code | ✅ Ready | No Streamlit deps in engines |
| Defensive iteration | ✅ Ready | Per v10.409 KeyError fix |
| FastAPI backend | ⚠️ Partial | App exists, cascade router missing |
| OpenAPI spec | ⚠️ Partial | Auto-generated but lacks cascade endpoints |
| CORS | ⚠️ TBD | Verify in v10.413 |
| JWT auth | ⚠️ TBD | Verify in v10.413 |
| Cascade-specific endpoints | ❌ Missing | v10.413 (E7) closes this |

**Bottom line: 80% React-ready.** The remaining 20% is the `utils/api_cascade.py` router which is exactly v10.413's scope. v10.412 onwards every batch follows the API-first pattern to avoid back-tracking.
