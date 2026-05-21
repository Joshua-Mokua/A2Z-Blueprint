# A2Z Blueprint MIS 360 — Master Prompt v5.40

**Updated:** 2026-05-21 (v10.496)
**Doctrine:** React Championship Transformation Phase F2 — design system complete.

---

## What v5.40 changes from v5.39

v5.39 opened the React championship transformation with v10.495 (foundations: Vite scaffolding, branding API, first runnable page). v5.40 closes phase **F2** — the design system is built. Every future React page composes from 8 primitive components. The MD Cockpit shell has been refactored to prove the composition works.

## Current state

| Metric | Value |
|---|---|
| Master prompt | **v5.40** |
| Latest batch | **v10.496** |
| Audit gates | **413** (G382 added this batch) |
| Verifier | 1153/1153 |
| Consecutive lockstep batches | **141** |
| Backend utils modules | 595 |
| Frontend files | **30** (16 from v10.495 + 14 from v10.496) |
| Frontend stack | React 18 + Vite 5 + TS strict + Tailwind 3 + TanStack Query 5 + React Router 6 |
| React design primitives | **8** (Button, Card, Input, Stat, Badge, Toast, Skeleton, Table) |
| New npm dependencies in v10.496 | **0** |

## Frontend architecture (post v10.496)

```
frontend/web/src/
├── App.tsx                          ← QC → Branding → Toast → Auth → WS → Router
├── main.tsx                         ← React DOM mount
├── index.css                        ← Tailwind + CSS variable defaults
├── lib/
│   ├── api.ts                       ← fetchBranding() and future API clients
│   ├── cn.ts                        ← Tailwind class-joiner utility
│   └── tokens.ts                    ← Design tokens (THE only place for semantic hex)
├── types/
│   ├── branding.ts                  ← /api/branding response type
│   └── components.ts                ← Shared Size/Variant/Tone types
├── providers/
│   ├── BrandingProvider.tsx         ← Fetches /api/branding, injects CSS vars
│   ├── AuthProvider.tsx             ← Stub (v10.497 implements)
│   └── WebSocketProvider.tsx        ← Stub (v10.498 implements)
├── hooks/
│   └── useBranding.ts               ← Branding context hook
├── components/                      ← Design system primitives
│   ├── Button.tsx
│   ├── Card.tsx
│   ├── Input.tsx
│   ├── Stat.tsx
│   ├── Badge.tsx
│   ├── Toast.tsx                    (also exports ToastProvider, useToast)
│   ├── Skeleton.tsx
│   └── Table.tsx
└── pages/
    ├── Dashboard.tsx                ← MD Cockpit (refactored v10.496)
    ├── Perform.tsx                  ← Placeholder for BSC scorecard
    ├── Profitability.tsx            ← Placeholder for customer/RM PnL
    └── Showcase.tsx                 ← Kitchen sink at /components
```

## Brand discipline (G381 + G382 enforced)

**G381 (since v10.495):** App.tsx contract literals preserved byte-for-byte. No hardcoded "Ecobank" string in `frontend/web/src/**.tsx`. BrandingProvider amendment present.

**G382 (since v10.496):** All 8 primitives exist. Dashboard.tsx imports from `@/components/*`. App.tsx contains `/components` route + ToastProvider. **No hardcoded hex colors in `src/components/**.tsx`** except `var(--brand-*)` patterns.

## Critical files (memory anchors)

### Backend (unchanged in v10.496)

| Path | Purpose |
|---|---|
| `app.py` | Streamlit entry |
| `utils/api.py` | FastAPI backend, port 8502 |
| `utils/api_branding.py` | `GET /api/branding` (v10.495) |
| `utils/config.py` | Tenant helpers including brand colors (v10.495) |
| `data/org_config.json` | Single source of tenant identity |

### Frontend (post v10.496)

| Path | Purpose |
|---|---|
| `frontend/web/src/App.tsx` | Provider chain + routes |
| `frontend/web/src/lib/tokens.ts` | **Single source for non-brand semantic hex** |
| `frontend/web/src/components/*.tsx` | The 8 design primitives |
| `frontend/web/src/pages/Showcase.tsx` | Living style guide at `/components` |
| `frontend/web/src/pages/Dashboard.tsx` | MD Cockpit (refactored to use primitives) |

## How to run (post v10.496)

### Two terminals (unchanged from v10.495)

**Terminal 1 — FastAPI backend:**
```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z
.venv\Scripts\activate
python -m utils.api
```

**Terminal 2 — React frontend:**
```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\frontend\web
pnpm dev
```

### Three URLs

- `http://localhost:5173/` — MD Cockpit shell (refactored, identical visual)
- `http://localhost:5173/components` — Kitchen sink showcase
- `http://localhost:8502/api/branding` — Tenant identity JSON

## Honest doctrine (carried + reinforced)

1. **Discovered prior work → honor not destroy.** (v10.495 App.tsx scaffolding)
2. **Phantom audit contracts → make real or remove.** (G46 → G381)
3. **Multi-tenant from day 1.** (tokens.ts separates tenant-specific brand from product-wide semantic)
4. **Single source of truth per concern.** (tokens.ts for semantic hex; BrandingProvider for brand; useBranding() for read access)
5. **Engines are pure-compute; transports are thin.** (Streamlit and FastAPI both call the same engines)
6. **No premature dependencies.** (v10.496 specifically did NOT install shadcn/ui CLI — same visual API by hand, zero new deps)
7. **Refactor proves the abstraction.** (Dashboard.tsx now composes from primitives; visual output unchanged but code is cleaner — this is the design system's first test, and it passes)

## Roadmap

| Phase | Batch | Scope | Status |
|---|---|---|---|
| F1 — Foundations | v10.495 | Vite + branding API + MD shell | ✅ Done |
| F2 — Design system | **v10.496** | 8 primitives + Showcase + Dashboard refactor | ✅ **This batch** |
| F3 — Auth | v10.497 ⏭️ | Login page → /api/auth/login → JWT → protected routes | Next |
| F3 — Enterprise shell | v10.498 ⏭️ | Sidebar + topbar + role-aware nav | |
| F4 — MD live data | v10.499 ⏭️ | /api/dashboard/md + Recharts | |
| F9-F10 — Testing | v10.500 ⏭️ | Vitest + Playwright + G383-G385 | |

After v10.500: progressive Streamlit → React migration of 158 pages.

---

**The hands begin to grip. The face has features.**

Tell me **"v10.496 live"** once `/components` renders and we proceed to v10.497 — JWT auth + login page.
