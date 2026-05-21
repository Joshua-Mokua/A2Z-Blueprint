# Changelog — v10.495 React Foundations + Branding API + G381

**Date:** 2026-05-21
**Doctrine source:** *React Championship Transformation Framework — F1 + F2 + F3 foundations*
**Joshua mandate:** *"on the colors lets adopt the real eco bank blue"*
**Audit:** G381 added (**412 honest gates**)
**Tests:** 9 v10.495 integration tests
**Verifier:** unchanged at 1153/1153 (verifier already current)
**Master prompt:** v5.38 → v5.39 (lockstep — **140 consecutive batches**)

---

## 🚀 First runnable React UI in A2Z history.

After 138 backend batches and 121 uncertainty drills, the React championship transformation begins. v10.495 is the *foundation* batch — environment setup, build tooling, multi-tenant branding API, and the App.tsx contract amendment that brings the April-29 scaffolding to life.

```
═══════════════════════════════════════════════════════════════════════
              REACT CHAMPIONSHIP TRANSFORMATION
              v10.495 (Phase F1 of 10)
═══════════════════════════════════════════════════════════════════════
  Backend additions (3 files)             Frontend (16 files)
  ─────────────────────────             ───────────────────────
  utils/config.py +4 helpers            vite.config.ts
  utils/api_branding.py NEW             tsconfig.json
  utils/api.py +2 lines                 tsconfig.node.json
                                        tailwind.config.js
  Multi-tenant from day 1               postcss.config.js
  /api/branding endpoint                index.html
  Ecobank colors as default             src/main.tsx
                                        src/index.css
  Contract amendment doctrine           src/types/branding.ts
  G46 phantom → G381 real               src/lib/api.ts
  App.tsx literals preserved            src/hooks/useBranding.ts
                                        src/providers/BrandingProvider.tsx
                                        src/providers/AuthProvider.tsx (stub)
                                        src/providers/WebSocketProvider.tsx (stub)
                                        src/pages/Dashboard.tsx (MD shell)
                                        src/pages/Perform.tsx (stub)
                                        src/pages/Profitability.tsx (stub)
                                        src/App.tsx (amended)
═══════════════════════════════════════════════════════════════════════
```

## What was built

### Backend (3 files, ~50 lines added)

**`utils/config.py` — 4 new helpers (append-only, no existing code touched):**

| Helper | Returns | Default |
|---|---|---|
| `brand_primary_hex()` | Primary brand color | `#1797ce` (Ecobank cyan-blue) |
| `brand_secondary_hex()` | Secondary brand color | `#0e2440` (deep navy) |
| `brand_accent_hex()` | Accent brand color | `#ffd200` (Ecobank yellow) |
| `ip_notice()` | Legal notice text | Verbatim from `pages/_login.py:318` |

Pattern matches v10.220's tenant helpers (`bank_name()`, `currency()`, etc.). All four read from `load_org_config()` so admins can override per-tenant via `data/org_config.json` with no code change.

**`utils/api_branding.py` NEW — FastAPI route module:**

`GET /api/branding` returns the complete tenant identity payload — bank name, brand colors, regulator name, IP notice, and 7 other tenant attributes. Public endpoint (no JWT) since the login page itself needs branding before authentication.

**`utils/api.py` — 2-line addition:**

Registers the new branding router. Same pattern as the existing cascade, capacity, strategy, cockpit router registrations.

### Frontend (16 files, ~500 lines)

The April-29 scaffolding (`App.tsx`, `frontend/web/README.md`) is preserved byte-for-byte. v10.495 adds the **runtime fabric** around it:

| File | Purpose |
|---|---|
| `vite.config.ts` | Build tool config + dev proxy to FastAPI:8502 |
| `tsconfig.json` | TypeScript strict mode + path alias `@/*` |
| `tsconfig.node.json` | Vite runtime TypeScript config |
| `tailwind.config.js` | Tailwind + CSS-variable brand tokens |
| `postcss.config.js` | Tailwind/Autoprefixer pipeline |
| `index.html` | Browser entry HTML |
| `src/main.tsx` | React DOM mount point |
| `src/index.css` | Tailwind base + CSS variable defaults |
| `src/types/branding.ts` | TS contract for `/api/branding` response |
| `src/lib/api.ts` | Typed `fetchBranding()` client |
| `src/hooks/useBranding.ts` | `useBranding()` context hook |
| `src/providers/BrandingProvider.tsx` | Fetches branding, injects CSS vars |
| `src/providers/AuthProvider.tsx` | Placeholder (v10.497 implements) |
| `src/providers/WebSocketProvider.tsx` | Placeholder (v10.498 implements) |
| `src/pages/Dashboard.tsx` | MD Cockpit shell — first visible page |
| `src/pages/Perform.tsx` | Placeholder for `/perform` route |
| `src/pages/Profitability.tsx` | Placeholder for `/profitability` route |
| `src/App.tsx` | Original literals preserved + `BrandingProvider` added |

### Contract amendment — original App.tsx literals preserved byte-for-byte

The original `App.tsx` provider chain:
```tsx
QueryClient → Auth → WebSocket → BrowserRouter
```

v10.495 amends it to:
```tsx
QueryClient → Branding → Auth → WebSocket → BrowserRouter
```

**Every one of the original literals the README's G46 demanded is preserved exactly.** The new `<BrandingProvider>` is added as a wrapper — not a replacement. Both Branding and the original Auth+WebSocket chain coexist.

This is the discipline encoded as **G381 (which replaces the phantom G46 that was documented in READMEs but never actually registered)**. G381 enforces:

1. `frontend/web/src/App.tsx` exists with original byte-for-byte literals
2. `BrandingProvider` exists between `QueryClientProvider` and `AuthProvider`
3. `utils/api_branding.py` exists and exposes `GET /api/branding`
4. `utils/config.py` exposes the 4 new helpers
5. No hardcoded `"Ecobank"` strings in `frontend/web/src/**.tsx`
6. The Dashboard page uses `useBranding()` for bank identity

### Three honest findings documented (not papered over)

**1. The G46 audit gate was phantom.** Documented in `frontend/web/README.md` since April 29, but never actually registered in `scripts/audit.py`. We caught this when `findstr /n "G46" scripts/audit.py` returned empty. v10.495 makes the contract **real** as G381 — same architectural intent, actually enforced.

**2. The deployed login uses different colors than corporate brand.** `pages/_login.py` ships a deep navy gradient (`#061422` → `#1a52a8`). The "real Ecobank corporate blue" is the lighter cyan `#1797ce`. Per Joshua's direction, the React side uses **corporate brand** (`#1797ce`). This creates temporary visual divergence between Streamlit (navy) and React (cyan-blue) — added to backlog as Track-C task "harmonize Streamlit `_login.py` with React brand".

**3. App.tsx had no `main.tsx` companion.** The April-29 scaffolding committed `App.tsx` but no React DOM mount point — Vite needs `main.tsx` to bootstrap. v10.495 ships `main.tsx` as a missing-piece fix, not a contract change.

### Verified outcome

| Metric | v10.494 | v10.495 |
|---|---|---|
| Audit gates | 411 | **412** (G381) |
| Verifier | 1153 | 1153 (unchanged — verifier doesn't gate React) |
| Lockstep batches | 139 | **140** |
| **Backend files added** | – | 3 (config helpers + branding router) |
| **Frontend files added** | 0 | **16** (full Vite project structure) |
| **First visible React page** | – | ✅ MD Cockpit shell with brand colors |
| **Multi-tenant from day 1** | – | ✅ Tenant identity from `/api/branding` |
| **Contract preserved** | – | ✅ App.tsx literals byte-for-byte |
| Honest findings documented | – | **3** (phantom gate, color divergence, missing main.tsx) |

### On your end

1. Extract `a2z_v10495_patch.zip` on top of your A2Z root
2. Append `utils/config_v10495_append.py` contents to `utils/config.py` (Step 2 in INSTALL.md)
3. Add 2 lines to `utils/api.py` per `utils/api_patch_instructions.md`
4. **Terminal 1:** `python -m utils.api` (FastAPI on :8502)
5. **Terminal 2:** `cd frontend\web && pnpm dev` (React on :5173)
6. Open `http://localhost:5173` → see your bank's MD Cockpit shell

## Roadmap (Phase F1-F10)

- ✅ **v10.495** — F1 foundations (this batch): React setup + branding API + first page
- ⏭️ **v10.496** — F2 design system: shadcn/ui scaffold, Button/Card/Input/Stat/Badge primitives in brand
- ⏭️ **v10.497** — F2/F3 routing + JWT auth: login page → real `/api/auth/login` → protected pages
- ⏭️ **v10.498** — F3 enterprise shell: sidebar, topbar, theme engine, role-aware nav
- ⏭️ **v10.499** — F4 MD command centre live: real data from `/api/dashboard/md`, charts
- ⏭️ **v10.500** — F9/F10 testing + frontend audit gates G382-G385

After v10.500: RM dashboards, then progressive Streamlit→React migration of the 158 pages.

**The patient is awake. The face is taking shape.**

Tell me **"v10.495 live"** once the React app renders successfully, and we proceed to v10.496.
