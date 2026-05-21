# A2Z MIS 360 — React SPA scaffolding

## Status

This subtree contains the **architectural skeleton** for the React SPA
specified in **Standard #37** of the master spec. It is NOT a runnable
build. It is here to:

  1. Pin the architectural decisions (provider chain, routing structure,
     state management library) before a frontend team starts work.
  2. Provide a verifiable contract — audit gate **G46** enforces that
     the spec-literal route paths, QueryClient import, and provider
     chain are preserved byte-for-byte.
  3. Document what the FastAPI backend already provides so the
     frontend team isn't designing endpoints from scratch.

## What's here

```
frontend/web/src/
  App.tsx         the spec-literal SPA entry — providers, routes, QueryClient
```

## What needs to be added to make this runnable

This is **deferred frontend work**, scoped separately from the Python
backend that v5.51 ships. To get this running:

### 1. Initialize the build

```bash
cd frontend/web
npm init -y
npm install react react-dom react-router-dom @tanstack/react-query
npm install -D typescript @types/react @types/react-dom vite
```

A Vite-based starter (`npm create vite@latest`) is the recommended
scaffold — it produces the `tsconfig.json`, `vite.config.ts`, and
`index.html` this directory tree expects.

### 2. Implement the placeholder components

App.tsx imports from:

  - `./providers/AuthProvider` — wraps the SPA with auth context;
    reads the JWT from localStorage and exposes a useAuth() hook.
    Must integrate with the existing FastAPI auth at `/api/v1/auth/*`.
  - `./providers/WebSocketProvider` — opens a WS connection to the
    `/ws/{user_id}` endpoint shipped in Standard #40
    (utils/websocket_manager.py). Exposes a useWebSocket() hook for
    real-time updates.
  - `./pages/Dashboard` — landing page after login
  - `./pages/Perform` — BSC performance view (consumes /api/v1/bsc/*)
  - `./pages/Profitability` — customer + RM profitability views
    (consumes /api/v1/profitability/* — backed by Volume Three engines)

### 3. Wire to the existing API

The Python backend shipped through v5.50 provides all the data the SPA
needs. **Do NOT design new endpoints — extend the existing surface.**

Relevant existing API areas (see utils/api.py):

  - `/api/v1/auth/*`            authentication
  - `/api/v1/bsc/*`             BSC actuals, targets, scorecards
  - `/api/v1/profitability/*`   customer + RM PnL (Volume Three)
  - `/api/v2/performance/insights/{staff_code}`  Standard #20
  - `/ws/{user_id}`             real-time updates (#40)

## Audit gate

**G46 `frontend_scaffolding_present`** verifies:

  - `frontend/web/src/App.tsx` exists
  - The spec literals are present byte-for-byte:
    - `import { QueryClient, QueryClientProvider } from '@tanstack/react-query'`
    - `const queryClient = new QueryClient()`
    - `<QueryClientProvider client={queryClient}>`
    - `<AuthProvider><WebSocketProvider><BrowserRouter>`
    - Route paths `/`, `/perform`, `/profitability`

A future frontend team replacing the placeholder components must
preserve these literals so the gate keeps passing — they ARE the
architectural contract.

## Spec deviation policy

The A2Z stack is Streamlit + Python (per Master_Prompt_v3.md
"Technology stack (mandatory)"). Volume Five's React SPA + React Native
specs are **explicitly additive** to the existing stack — the Streamlit
admin pages stay (Standard #39), and the React SPA is for executives,
managers, and staff.

Until a frontend team picks this up, all production traffic continues
to go to the Streamlit pages. This scaffolding does not replace
anything; it's a contract for future work.
