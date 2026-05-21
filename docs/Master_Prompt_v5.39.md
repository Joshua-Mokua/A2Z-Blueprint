# A2Z Blueprint MIS 360 — Master Prompt v5.39

**Updated:** 2026-05-21 (v10.495)
**Doctrine:** React Championship Transformation begins. Backend platform stable.

---

## What v5.39 changes from v5.38

v5.38 closed the Backend Maturity arc at 411 audit gates and the 121-drill Elite Uncertainty Exposure campaign. v5.39 opens the **React Championship Transformation** — 10 phases (F1-F10) that take A2Z from a Streamlit-only stack to a production-grade React SPA with progressive Streamlit retirement.

**v10.495 lands phase F1** (foundations): React + Vite + TypeScript + Tailwind scaffolding, multi-tenant branding API (`GET /api/branding`), and the App.tsx contract amendment that wires the April-29 scaffolding to a runnable Vite build.

## Current state

| Metric | Value |
|---|---|
| Master prompt | **v5.39** |
| Latest batch | **v10.495** |
| Audit gates | **412** (G381 added — replaces phantom G46) |
| Verifier | 1153/1153 |
| Consecutive lockstep batches | **140** |
| Backend utils modules | 595 |
| Backend LOC | ~369K |
| Frontend files | **16** (new this batch) |
| Frontend stack | React 18 + Vite 5 + TS strict + Tailwind 3 + TanStack Query 5 + React Router 6 |
| First runnable React UI | ✅ MD Cockpit shell (`/`) |

## Champion architecture decisions encoded

### Backend (stable since v10.494, untouched in v10.495)

- **PostgreSQL primary, JSON fallback** (`utils/db.py` dual-mode)
- **FastAPI on port 8502**, Streamlit on 8501 (run separately or via `run_all.bat`)
- **JWT auth on every endpoint except `/api/health` and `/api/branding`** (the latter is new — public by design since the login page needs branding before auth)
- **Engine pattern**: pure-compute engines in `utils/*_engine.py`, surfaced through both Streamlit pages AND FastAPI endpoints (single source of truth)
- **G128+ audit baseline**: structural rules + standards registry + scenario library
- **121-drill Elite Uncertainty Exposure** doctrine: every engine must declare its uncertainty bounds

### Frontend (new this batch — F1 of F10)

- **Vite 5 + React 18 + TypeScript strict** — no Create React App, no JS-only
- **Tailwind 3 + CSS variables for brand tokens** — multi-tenant from day 1, no recompile to change colors
- **TanStack Query 5** — already imported in App.tsx contract; future batches use it for /api/* fetches
- **React Router 6 with BrowserRouter** — three routes today (`/`, `/perform`, `/profitability`)
- **Provider chain (G381)**:
  ```
  QueryClient → Branding → Auth → WebSocket → BrowserRouter
  ```
  — Branding outside Auth so the future login page can render bank identity unauthenticated
- **No hardcoded bank-name strings in .tsx** (G381 enforces) — everything reads from `/api/branding`
- **Path alias `@/*` for src imports** — cleaner than `../../lib/api`

### Multi-tenant from day 1

Three layers:
1. **utils/config.py helpers** read from `data/org_config.json` with documented Ecobank fallbacks
2. **GET /api/branding** returns the full identity payload as JSON
3. **BrandingProvider** fetches it once on mount, injects CSS variables, exposes via `useBranding()` hook

Change `data/org_config.json` → restart → entire UI reflects the new tenant. Zero code changes.

### Brand identity (Ecobank corporate, per Joshua direction)

| Token | Hex | Use |
|---|---|---|
| `--brand-primary` | `#1797ce` | Primary actions, KPI card borders, focus rings |
| `--brand-secondary` | `#0e2440` | Top bar, headers, dark backgrounds |
| `--brand-accent` | `#ffd200` | Alerts, highlights, "new" badges |

**Known divergence**: deployed Streamlit `_login.py` uses a different navy gradient (`#061422 → #1a52a8`). Backlog Track-C task to harmonize the Streamlit login with corporate brand once React is fully proven.

## How to run (v10.495+)

### Local development — two terminals

**Terminal 1 — FastAPI backend:**
```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z
python -m utils.api
```

Expect: `Uvicorn running on http://0.0.0.0:8502` and `A2Z API — branding router mounted at /api/branding`.

**Terminal 2 — React frontend:**
```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\frontend\web
pnpm dev
```

Expect: `VITE v5.x.x ready in ~800ms` and `Local: http://localhost:5173/`.

Browser at `http://localhost:5173/` shows the MD Cockpit shell with Ecobank-branded header, three placeholder KPI cards, and the IP notice footer.

### Streamlit still works

The 158 existing Streamlit pages are completely unchanged. Run them as always:
```
streamlit run app.py
```
Both stacks can run in parallel during the migration. **No Streamlit pages are deprecated yet.**

## Roadmap — React Championship Transformation

| Phase | Batch | Scope |
|---|---|---|
| F1 — Foundations | **v10.495 ✅** | Vite+TS+Tailwind+TanStack+Router setup, `/api/branding`, MD shell |
| F2 — Design system | v10.496 ⏭️ | shadcn/ui components in Ecobank brand: Button, Card, Input, Stat, Badge, Toast |
| F3 — Auth + Routing | v10.497 ⏭️ | Login page → `/api/auth/login` → JWT → protected routes |
| F3 — Enterprise shell | v10.498 ⏭️ | Sidebar, topbar, role-aware nav, theme engine |
| F4 — MD command centre live | v10.499 ⏭️ | Real `/api/dashboard/md` data, Recharts viz |
| F9-F10 — Testing + audit | v10.500 ⏭️ | Vitest unit, Playwright e2e, G382-G385 |

After v10.500: RM dashboards (v10.501-v10.520), then progressive Streamlit→React page migration.

## Honest doctrine (carried from v5.38, reinforced this batch)

1. **Discovered prior work → honor not destroy.** App.tsx and offlineSync.ts existed from April 29. We preserved every byte and added BrandingProvider as a documented amendment.
2. **Phantom audit contracts → make real or remove.** G46 was documented but never registered. v10.495 ships it as a real G381.
3. **Multi-tenant from day 1.** Even though Joshua's only deployment is Ecobank Kenya, every helper reads from config. Zero hardcoded strings.
4. **Single source of truth per concern.** `utils/config.py` owns tenant identity. `kpi_library.json` owns KPI definitions. `bank_targets.json` owns MD targets. `target_cascade.json` owns staff targets.
5. **Engines are pure-compute, transports are thin.** Streamlit pages call engines; FastAPI endpoints call engines; React calls FastAPI which calls engines. The engine is the source of truth.
6. **App.tsx amendments documented, not silent.** The G381 codifies which literals are byte-for-byte protected and which structural additions are allowed.
7. **Streamlit stays until React proves itself.** No Streamlit page is deleted until its React replacement is verified at production.

## Critical files (memory anchors)

| Path | Purpose |
|---|---|
| `app.py` | Streamlit entry (has `_APP_VERSION` stamp that wipes stale managers on code update) |
| `utils/api.py` | FastAPI backend, port 8502 |
| `utils/api_branding.py` | **v10.495 NEW** — `GET /api/branding` |
| `utils/config.py` | Tenant helpers (extended v10.495 with brand colors + ip_notice) |
| `utils/core.py` | All managers (UserManager, CascadeManager, etc.) |
| `data/org_config.json` | Single source of tenant identity |
| `data/kpi_library.json` | Canonical KPI definitions |
| `pages/_login.py` | Streamlit login (source of verbatim IP notice text) |
| `frontend/web/src/App.tsx` | **v10.495 amended** — React entry + provider chain |
| `frontend/web/src/providers/BrandingProvider.tsx` | **v10.495 NEW** — fetches /api/branding |
| `frontend/web/src/pages/Dashboard.tsx` | **v10.495 NEW** — MD Cockpit shell |
| `scripts/audit.py` | All 412 audit gates |

## Standing permissions (carried)

- **"continue"** = proceed to the next batch in the doctrine without individual approval
- **Engines must declare uncertainty bounds** (the 121-drill doctrine)
- **No hardcoded `"Ecobank"` strings in .tsx** (G381 — use `useBranding()` hook)
- **App.tsx contract literals are sacred** (G381 — preserved byte-for-byte)
- **No silent contract changes** — every amendment documented in CHANGELOG and enforced by a gate

---

**The patient is awake. The face is taking shape. The hands begin to move.**

Tell me **"v10.495 live"** once you see the React app render. Then we proceed to v10.496 — Design System + shadcn/ui components.
