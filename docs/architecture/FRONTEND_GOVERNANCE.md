# A2Z Blueprint MIS 360 — Frontend Governance

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md` + `ROLE_GOVERNANCE.md` + `RBAC_MATRIX.md`)
**Status:** `canonical` (post v10.497 P0 shadcn pivot)
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 4)
**Last updated:** 2026-05-24 (revised v10.499 Stage C Batch 2d — `useRole_hook_contract` restructured to Implementation v1 + Future extensions per CGR1; previous revisions: Batch 2c renamed /api/roles/me → /api/roles/registry, Batch 2a reclassified shadcn pivot ASPIRATIONAL)
**Owner:** Frontend / Design System
**Authoritative sources:**

- `frontend/web/src/lib/tokens.ts` (semantic hex)
- `data/org_config.json` (brand colors)
- ~~`frontend/web/components.json` (shadcn config)~~ — **ASPIRATIONAL; file not present at commit `49e804f`** (see CGR1 reality-check below)
- `frontend/web/tailwind.config.js` (Tailwind extends)
- `frontend/web/src/index.css` (CSS variable bindings)

**Machine-readable equivalent:** `FRONTEND_GOVERNANCE.json`

---

## CGR1 Reality-Check Correction (v10.499 Stage C Batch 2a)

**Date:** 2026-05-22
**Inspected by:** Claude session, ground-checked against fresh repo clone (commit `49e804f`)
**Doctrine status correction:** described-as-active → ASPIRATIONAL with grace window

This artifact, as authored in v10.497 Stage B Wave 4, described the React frontend as running on **shadcn/ui (new-york style, neutral baseColor)** with 11 shadcn primitives in `frontend/web/src/components/ui/`. Per CGR1 doctrine, every claim must be classifiable as ACTIVE, TRANSITIONAL, or ASPIRATIONAL — and that classification must be verifiable by code inspection. Direct inspection of the repo tree at commit `49e804f` reveals:

- **No `frontend/web/components.json`** — shadcn's canonical config marker file does not exist.
- **No `frontend/web/src/components/ui/` subdirectory** — the canonical location for shadcn primitives does not exist.
- **8 bespoke v10.496 primitives** sit flat in `frontend/web/src/components/`: `Button.tsx`, `Badge.tsx`, `Card.tsx`, `Input.tsx`, `Skeleton.tsx`, `Stat.tsx`, `Table.tsx`, `Toast.tsx`. Each carries a v10.496 file header and a bespoke variant API.
- `Button.tsx` exposes `variant: primary | secondary | ghost | danger` — bespoke, not shadcn's `default | destructive | outline | secondary | ghost | link`.
- Toast notifications are handled by a bespoke `ToastProvider` in `components/Toast.tsx` — not by `sonner`.
- `App.tsx`'s provider chain references `ToastProvider`, not the shadcn/sonner `Toaster`.

The shadcn pivot was described in v10.497 P0 (commit `4b27c1c` in the REVIVAL_LEDGER), declared canonical in this artifact, and echoed in the SESSION_BOOTSTRAP. Three doctrinal sources agreed; the filesystem disagreed.

### Classification correction

| Claim                                       | Previous classification        | Corrected classification                                    |
| ------------------------------------------- | ------------------------------ | ----------------------------------------------------------- |
| shadcn/ui is the canonical component system | described as active state      | **ASPIRATIONAL** — scoped as future arc                     |
| 11 shadcn primitives in `components/ui/`    | described as shipped           | **ASPIRATIONAL** — not present in tree                      |
| `components.json` shadcn config             | listed as authoritative source | **DOES NOT EXIST** — removed from authoritative-source list |
| Bespoke v10.496 primitives in `components/` | implicitly deprecated          | **CANONICAL — current React component layer**               |
| `sonner` for toasts                         | declared in stack              | **ASPIRATIONAL** — bespoke `ToastProvider` is canonical     |

### What is canonical right now (current React component reality)

- **Component primitives**: 8 bespoke v10.496 primitives in `frontend/web/src/components/`
  - `Button` — variants: `primary | secondary | ghost | danger`; sizes; loading state
  - `Badge`, `Card`, `Input`, `Skeleton`, `Stat`, `Table`, `Toast`
- **Toast system**: bespoke `ToastProvider` from `components/Toast.tsx`
- **Hooks**: `hooks/useBranding.ts` (single hook currently shipped)
- **Providers**: `BrandingProvider`, `AuthProvider`, `WebSocketProvider`
- **Pages**: `Dashboard.tsx`, `Perform.tsx`, `Profitability.tsx`, `Showcase.tsx`
- **App.tsx provider chain (canonical order)**: `QueryClientProvider → BrandingProvider → ToastProvider → AuthProvider → WebSocketProvider → BrowserRouter`
- **Token discipline chain**: `tokens.ts (hex source) → index.css (CSS vars) → tailwind.config.js (wrappers) → components (Tailwind utility classes)` — this chain is intact and operational, independent of whether the underlying primitives are shadcn or bespoke.

### Grace window for shadcn migration

If the shadcn/ui pivot is genuinely desired going forward, it is now scoped as a **discrete future arc**:

- Its own batch (or set of batches) under the v10.5xx series
- Its own gate (`gate_shadcn_primitives_complete` or similar)
- Its own ledger entry recording the arc's start, milestones, and completion
- Migration is a tree change (introduce `components/ui/`, move bespoke `components/*` callsites to consume new primitives, retire bespoke components in same batch they're replaced)
- The bespoke v10.496 primitives stay canonical until that arc completes — they are not deprecated by the pivot's mere intention, only by the pivot's actual completion

Until then: **every React change consumes the bespoke v10.496 primitives.** Step 1.4's `useRole()` hook, the forthcoming protected-route wrapper, and any new pages must follow this rule. The mistake to avoid: importing shadcn components that don't exist, or writing component code that assumes shadcn's variant API.

### Standing reality-check procedure (per CGR1)

Any future update to this artifact's classification of the component system must be preceded by:

1. Direct inspection of `frontend/web/src/components/` and `frontend/web/components.json`
2. Comparison of inspection output against the claim being added
3. Classification of the claim (ACTIVE / TRANSITIONAL / ASPIRATIONAL)
4. Update to `GOVERNANCE_REALITY_INDEX.md` with date and source of reality check

The Batch 2a procedure that surfaced this shadcn drift is the canonical example. The mechanical version — `scripts/session_vitals.py`, planned for v10.500 — will make this procedure automatic at session-open time.

---

## Purpose

This document is the canonical contract for both frontends of A2Z:

- **React app** (`frontend/web/`) — the new canonical UI, built on shadcn/ui (post v10.497 P0 pivot)
- **Streamlit pages** (`pages/*.py`) — the existing 158-page surface, `transitional` (will migrate to React post v10.500)

It declares:

- Design token discipline (tokens.ts → index.css → Tailwind → components)
- Component system (shadcn primitives + A2Z extensions)
- Brand color flow (tenant-injected, never hardcoded)
- Role-driven rendering contract (`useRole()` hook — resolves OI-9)
- API client conventions
- Multi-tenant identity rules
- Streamlit migration policy

---

## Doctrine

**FE1 — Single component system.** shadcn/ui is the only governed primitive library. No parallel architectures. No bespoke replacements for shadcn-installed components.

**FE2 — Tokens flow downward.** `tokens.ts` is source. `index.css` is `derived`. Tailwind config wraps. Components consume Tailwind classes. No component reads hex directly from anywhere else.

**FE3 — Brand identity is tenant data, never code.** Brand colors and tenant strings live in `data/org_config.json`. The frontend learns them at runtime via `GET /api/branding`. No "Ecobank" or any tenant string in `frontend/web/src/**.tsx`.

**FE4 — Role-driven rendering goes through `useRole()`.** Direct role-string comparisons in React (`if (user.role === "MD")`) are violations. Use `useRole().hasCapability("...")`.

**FE5 — Cross-page imports are forbidden.** Pages may import from `components`, `lib`, `providers`. Pages may NOT import from other pages. Components may NOT import pages.

**FE6 — A2Z extensions preserve shadcn defaults.** Extensions like `Button.loading` and `Badge.tone` add capabilities without removing shadcn's `variant=` system. Both work simultaneously.

---

## React frontend — `frontend/web/`

### Stack

| Layer                | Choice                                        | Version (target)                           |
| -------------------- | --------------------------------------------- | ------------------------------------------ |
| Framework            | React                                         | 18+                                        |
| Build tool           | Vite                                          | latest                                     |
| Language             | TypeScript                                    | latest                                     |
| Component primitives | shadcn/ui (new-york style, neutral baseColor) | installed via `pnpm dlx shadcn@latest add` |
| Styling              | Tailwind CSS + CSS variables                  | 3.x                                        |
| Class composition    | clsx + tailwind-merge                         | via `@/lib/cn`                             |
| Icons                | lucide-react                                  | 0.383+                                     |
| Toasts               | sonner                                        | latest                                     |
| Data fetching        | (TBD — likely React Query or SWR)             | future                                     |
| Routing              | (TBD per App.tsx)                             | future                                     |

### File structure (post v10.497 P0)

```
frontend/web/
├── components.json              # shadcn config (canonical)
├── tailwind.config.js           # Tailwind extends (canonical)
├── vite.config.ts               # Vite + dev proxy to :8502
├── tsconfig.json
├── package.json
└── src/
    ├── lib/
    │   ├── tokens.ts            # ★ SEMANTIC HEX SOURCE
    │   ├── cn.ts                # class composition (clsx + tailwind-merge)
    │   └── api.ts               # API client
    ├── components/
    │   ├── ui/                  # ★ shadcn primitives (11 files)
    │   │   ├── button.tsx
    │   │   ├── badge.tsx
    │   │   ├── card.tsx
    │   │   ├── input.tsx
    │   │   ├── label.tsx
    │   │   ├── alert.tsx
    │   │   ├── skeleton.tsx
    │   │   ├── table.tsx
    │   │   ├── dialog.tsx
    │   │   ├── form.tsx
    │   │   └── sonner.tsx
    │   ├── StatCard.tsx         # A2Z composition (KPI tile)
    │   └── (other components)
    ├── providers/
    │   ├── BrandingProvider.tsx # tenant-aware brand colors
    │   ├── AuthProvider.tsx     # (transitional — Phase 2 v10.497)
    │   └── (other providers)
    ├── pages/
    │   ├── Dashboard.tsx
    │   ├── Showcase.tsx
    │   └── (others)
    ├── App.tsx                  # Provider chain
    ├── index.css                # ★ derived from tokens.ts
    └── main.tsx
```

(**OI-35** — full enumeration of pages and components pending Joshua's `dir /s /b frontend\web\src` output.)

### Token discipline (the four-step chain)

```
1. tokens.ts (HEX, semantic) — SOURCE
       ↓
2. index.css (HSL components in CSS vars) — DERIVED
       ↓
3. tailwind.config.js (hsl(var(--token) / <alpha-value>)) — WRAPPED
       ↓
4. components use Tailwind classes — CONSUMED
```

**Critical lesson from v10.497 P0:**

shadcn's opacity modifiers (`bg-primary/90`, `text-muted-foreground/50`) require the CSS variables to be **HSL components** (e.g. `197 80% 45%`), not hex. The Tailwind config wraps them with `hsl(var(--token) / <alpha-value>)` syntax. If the CSS vars are hex, opacity modifiers silently break.

`tokens.ts` stays in hex (the semantic source). `index.css` is the derived layer with HSL components. The build doesn't auto-convert; it's manually maintained — the rule is: when you change `tokens.ts`, update `index.css` in the same commit.

### Brand vs theme variables

**Brand variables** (tenant identity, injected at runtime by BrandingProvider):

```css
:root {
  --brand-primary: #007fa3; /* HEX, set by BrandingProvider */
  --brand-secondary: #ffc845;
  --brand-accent: #5c2d91;
}
```

**Theme variables** (shadcn semantic, sourced from tokens.ts):

```css
:root {
  --primary: 197 80% 45%; /* HSL components, derived */
  --primary-foreground: 0 0% 100%;
  --background: 0 0% 100%;
  --foreground: 222 47% 11%;
  --muted: 210 40% 96%;
  --muted-foreground: 215 16% 47%;
  /* ...etc */
}
```

Tailwind config:

```javascript
theme: {
  extend: {
    colors: {
      brand: {
        primary: 'var(--brand-primary)',
        secondary: 'var(--brand-secondary)',
        accent: 'var(--brand-accent)',
      },
      primary: {
        DEFAULT: 'hsl(var(--primary) / <alpha-value>)',
        foreground: 'hsl(var(--primary-foreground) / <alpha-value>)',
      },
      // ...
    },
  },
},
```

This dual system lets components use:

- `text-brand-primary` for tenant-injected hex (no opacity modifiers possible — hex doesn't support `/`)
- `bg-primary/90` for shadcn semantic with opacity (works because HSL components)

### Component system

#### shadcn primitives (11 installed)

| Primitive        | Source | A2Z extension                                                              |
| ---------------- | ------ | -------------------------------------------------------------------------- |
| `Button`         | shadcn | `loading` prop (inline spinner + aria-busy + implicit disable)             |
| `Badge`          | shadcn | `tone` variants (success / warning / danger / info / brand / neutral)      |
| `Card`           | shadcn | none (composed by StatCard)                                                |
| `Input`          | shadcn | none                                                                       |
| `Label`          | shadcn | none                                                                       |
| `Alert`          | shadcn | none                                                                       |
| `Skeleton`       | shadcn | none                                                                       |
| `Table`          | shadcn | none                                                                       |
| `Dialog`         | shadcn | none                                                                       |
| `Form`           | shadcn | none                                                                       |
| `Sonner` (toast) | shadcn | richColors + closeButton + position="top-right" via `<Toaster>` in App.tsx |

#### A2Z compositions

| Component  | Purpose                                       | Composed from               |
| ---------- | --------------------------------------------- | --------------------------- |
| `StatCard` | KPI tile (label, value, delta, accent stripe) | shadcn Card + custom layout |

(**Future A2Z extensions** require justification in this article + addition to the table.)

### A2Z extension contract

When extending shadcn primitives:

1. **Preserve original API** — `variant=`, `size=`, `className=`, etc. must continue working
2. **Add as new props** — extensions are additive (`tone=`, `loading=`)
3. **Document in this article** — every extension declared here
4. **Self-test** — extensions have visual verification in Showcase.tsx

Example pattern (Button):

```tsx
// Original shadcn API preserved
<Button variant="outline" size="lg" onClick={handle}>Save</Button>

// A2Z extension adds loading
<Button variant="outline" size="lg" loading={isSaving} onClick={handle}>Save</Button>

// Both compose
<Button variant="ghost" loading={isLoading}>Cancel</Button>
```

### Provider chain (App.tsx)

```tsx
<QueryClientProvider client={queryClient}>
  <BrandingProvider>
    <ToastProvider>
      <AuthProvider>
        <RoleProvider>
          <WebSocketProvider>
            <BrowserRouter>{/* pages */}</BrowserRouter>
          </WebSocketProvider>
        </RoleProvider>
      </AuthProvider>
    </ToastProvider>
  </BrandingProvider>
</QueryClientProvider>
```

Constraints (per Stage C `gate_app_tsx_contract` / G381):

- Order of providers preserved byte-for-byte
- No tenant string literal anywhere in App.tsx
- `BrandingProvider` wraps everything below `QueryClientProvider` (brand colors are CSS vars used by all descendants)
- `ToastProvider` (bespoke v10.496, not shadcn `Toaster`) sits inside `BrandingProvider` so toasts can use brand colors
- `RoleProvider` (Batch 2d) sits inside `AuthProvider` (depends on JWT cookie set by auth flow) and outside `WebSocketProvider` (so WebSocket subscriptions can read role data for channel scoping)

### Routing

(**OI-36** — Router specification (likely React Router) to be documented in Wave 4 amendment after full App.tsx tree is surveyed.)

---

## React Phase 2 contract — `useRole()` hook (resolves OI-9)

**Status:** ACTIVE (Implementation v1 shipped v10.499 Stage C Batch 2d)

**Implementation files:**

- `frontend/web/src/hooks/useRole.ts` — consumer hook (6 LOC)
- `frontend/web/src/providers/RoleProvider.tsx` — provider with parallel fetch (~150 LOC)
- `frontend/web/src/types/role.ts` — TypeScript contracts (validated against backend runtime output)
- `frontend/web/src/lib/api.ts` — `fetchWhoamiDetailed` + `fetchRoleRegistry` client functions
- `frontend/web/src/App.tsx` — provider mounted between AuthProvider and WebSocketProvider

This is the canonical React contract for consuming role data from the backend. Path A architecture chosen over Path B: matches the existing `useBranding`/`BrandingProvider` context-Provider pattern rather than introducing `useQuery` (TanStack Query is installed at App level but not yet adopted for data fetching).

### Implementation v1 — what shipped in Batch 2d

Hook surface (from `useRole.ts` consuming `RoleProvider`):

    import { useRole } from "@/hooks/useRole";

    const {
      user,            // UserIdentity | null  — from /api/auth/whoami-detailed
      registry,        // RoleRegistry | null  — from /api/roles/registry
      loading,         // boolean              — true until both fetches resolve
      error,           // string | null        — surfaces fetch failure (e.g. 401)

      isAdmin,         // boolean — derived: user?.is_admin ?? false
      canViewAll,      // boolean — derived: user?.can_view_all ?? false
      canBeTagged,     // boolean — derived: user?.can_be_tagged ?? false
      isAuthenticated, // boolean — derived: user !== null && error === null

      userHasTier,     // (tier: Tier) => boolean
      userHasAnyRole,  // (roles: string[]) => boolean
    } = useRole();

User shape (subset of `UserIdentity`):

    {
      username:           string;
      staff_code:         string;
      full_name:          string;
      department:         string;
      email:              string | null;
      active:             boolean;
      role:               string;
      tier:               Tier;          // 5-tier enum
      sbu:                Sbu;           // 7-SBU enum
      branch_scope:       BranchScope;   // branch_bound | head_office | national
      matched_via:        string;        // 'explicit' or 'keyword_fallback:<keyword>'
      can_be_tagged:      boolean;
      is_admin:           boolean;
      can_view_all:       boolean;
      accessible_modules: string[];      // Streamlit RBAC migration-compat
      hidden_modules:     string[];
      expires_at:         string | null; // ISO 8601 datetime
    }

### Data sources (live as of Batch 2d)

    GET /api/auth/whoami-detailed   — caller's identity (shipped Batch 2b)
    GET /api/roles/registry         — canonical role registry (shipped Batch 2c)

Both endpoints sit behind `Depends(get_current_user)`. The provider's `Promise.all` fetches them in parallel on mount.

### Caching semantics

The Provider runs both fetches once on mount (`useEffect` with empty dependency array). No automatic refetch, no stale-while-revalidate, no focus-refresh — this is the v10.495 `useBranding` pattern intentionally. If TanStack Query adoption becomes a stack-wide decision (separate batch), the Provider can be migrated to `useQuery` with `staleTime: 5min` then.

Invalidation hooks for future:

- On logout → unmount/remount the provider tree (clears all state)
- On token refresh → provider re-mount or explicit refetch (TBD when auth lands)

### Stage C enforcement (planned)

| Gate                                | Verifies                                                                             | Severity |
| ----------------------------------- | ------------------------------------------------------------------------------------ | -------- |
| `gate_useRole_hook_used`            | Components using role data go through `useRole()`, not raw fetches                   | MEDIUM   |
| `gate_no_role_string_comparison`    | No `user.role === "MD"` or other direct role-string compares                         | HIGH     |
| `gate_role_endpoint_contract_match` | `UserIdentity`/`RoleRegistry` types in `types/role.ts` match backend response shapes | HIGH     |

### Forbidden patterns (HIGH severity)

Direct role-string comparison (forbidden):

    if (user.role === "Chief Executive & Managing Director") { ... }

Hardcoded role aliases (forbidden):

    if (user.role === "MD") { ... }

Inventing tier values not on the profitability axis (forbidden):

    if (role.tier === "executive") { ... }   // 'executive' is an SBU, not a tier

Canonical enum comparison (correct):

    if (userHasTier("structural_owner")) { ... }

Derived flags (correct):

    if (isAdmin) { ... }

Any-of role matching (correct):

    if (userHasAnyRole(["Managing Director", "Director Retail Banking"])) { ... }

### Future extensions (ASPIRATIONAL)

The original Stage B aspirational signature declared additional features that did NOT ship in v1. Each is deferred to a future batch with its own architectural sub-decisions to make. Tracked as open items:

| Field/method             | Status       | Open item | Rationale for deferral                                                                                                             |
| ------------------------ | ------------ | --------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `seniorityTier: 0..6`    | ASPIRATIONAL | OI-59     | Requires `_resolve_seniority_tier` mapping in `role_taxonomy.py`; depends on canonical 0-6 mapping decision                        |
| `capabilities: string[]` | ASPIRATIONAL | OI-60     | Requires `utils/rbac_matrix.py` module with `resolve_capabilities` (planned per Stage C OI-11); module does not yet exist          |
| `hasCapability(cap)`     | ASPIRATIONAL | OI-60     | Depends on `capabilities` array shipping first                                                                                     |
| `isMD()` convenience     | ASPIRATIONAL | OI-61     | Trivial wrapper over `userHasAnyRole(["Managing Director"])` once role canonicalisation is settled; not yet needed by any consumer |
| `isChief()` convenience  | ASPIRATIONAL | OI-61     | Depends on seniorityTier shipping; depends on chief-role definition                                                                |
| `displayName` field      | ASPIRATIONAL | OI-62     | Endpoint currently returns `full_name`; future renaming/aliasing is a contract-change requiring coordinated React + backend update |
| TanStack Query adoption  | ASPIRATIONAL | OI-63     | Stack-wide migration decision; useBranding would need migration too to maintain consistency                                        |

Per CGR1 doctrine, **doctrine bends to reality, not reality to doctrine**. The v1 implementation reflects what `role_taxonomy.py` actually exposes today (`tier`, `branch_scope`, `sbu`, `can_be_tagged`) and what the backend endpoints actually return (`is_admin`, `can_view_all`, `accessible_modules`). The aspirational features remain valuable but each is a deliberate future batch, not a Batch 2d gap to fill in retroactively.

### Implementation reference: Provider sketch

The actual `RoleProvider.tsx` is the canonical reference. Documentation sketch:

    // frontend/web/src/providers/RoleProvider.tsx
    import { createContext, useEffect, useState } from 'react';
    import { fetchWhoamiDetailed, fetchRoleRegistry } from '@/lib/api';

    export function RoleProvider({ children }) {
      const [user, setUser]         = useState(null);
      const [registry, setRegistry] = useState(null);
      const [loading, setLoading]   = useState(true);
      const [error, setError]       = useState(null);

      useEffect(() => {
        Promise.all([fetchWhoamiDetailed(), fetchRoleRegistry()])
          .then(([u, r]) => { setUser(u); setRegistry(r); })
          .catch((e) => setError(String(e)))
          .finally(() => setLoading(false));
      }, []);

      const value = {
        user, registry, loading, error,
        isAdmin:         user?.is_admin ?? false,
        canViewAll:      user?.can_view_all ?? false,
        canBeTagged:     user?.can_be_tagged ?? false,
        isAuthenticated: user !== null && error === null,
        userHasTier:    (tier)  => user?.tier === tier,
        userHasAnyRole: (roles) => {
          if (!user) return false;
          const ur = user.role.toLowerCase();
          return roles.some(r => r.toLowerCase() === ur);
        },
      };

      return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
    }

---

## API client conventions

`frontend/web/src/lib/api.ts` is the canonical HTTP client.

### Cookie-based authentication

After v10.497 P1.3, the API uses **httpOnly cookie** for session. Fetch must include `credentials: 'include'`:

```typescript
export const api = {
  async get<T>(path: string): Promise<T> {
    const res = await fetch(path, {
      credentials: "include", // ← critical for cookie auth
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },
  async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },
};
```

### Error handling

`ApiError` is the canonical exception type. 401 errors trigger logout via `AuthProvider`. 403 errors are surfaced to the user via sonner toast.

### Vite dev proxy

`vite.config.ts` proxies `/api/*` to `http://localhost:8502` (FastAPI dev server). No `VITE_API_URL` env var needed in dev. Production deployments configure via build-time env.

---

## Streamlit pages — `pages/*.py`

### Current state

158 Streamlit pages per Master Prompt v5.40. Each uses `utils/auth.py::require_access(module_name)` (and the colliding `require_role` alias) for page-level RBAC.

Known canonical pages (from session memory):

| Page                  | Purpose             | Module name |
| --------------------- | ------------------- | ----------- |
| `pages/1_perform.py`  | BSC scorecard       | `bsc`       |
| `pages/3_pipeline.py` | CRM pipeline        | `pipeline`  |
| `pages/7_admin.py`    | Admin + KPI Library | `admin`     |
| `pages/12_cascade.py` | Target cascade      | `cascade`   |
| `pages/15_cbs.py`     | CBS explorer        | `cbs`       |

Full inventory: OI-13 (Wave 3) — to be enumerated in follow-up batch.

### Classification: `transitional`

Per `CANONICAL_TRUTH_REGISTRY.md::streamlit_page_access_rbac`:

- Status: `transitional`
- Transition target: `deprecated` (post v10.500)
- Migration strategy: progressive page-by-page migration to React

### Migration policy

When a Streamlit page is migrated to React:

1. New React page authored under `frontend/web/src/pages/`
2. Uses shadcn primitives + A2Z extensions + `useRole()`
3. Streamlit page marked deprecated in this document with `superseded_by` pointer
4. After 1 batch with both UIs operational, Streamlit page is removed
5. `users.json::accessible_modules` field stays (still used by remaining Streamlit pages)

### Streamlit-specific governance

- `utils/page_shared.py` is the canonical helper module for Streamlit pages
- `utils/page_smoke.py` is the canonical smoke test runner
- `utils/page_manifest_loader.py` loads page metadata
- `utils/page_cockpit_render.py` renders cockpit-style pages

`gate_page_smoke_test` (scripts/audit.py:33164) enforces every Streamlit page must pass smoke tests.

### Streamlit toast usage

Streamlit pages should use `st.toast()` for transient feedback, consistent with React's sonner. Avoid `st.success()`/`st.warning()` blocks for short-lived feedback (those are for in-page status, not floating notifications).

---

## Multi-tenant identity rules

Per `SYSTEM_CONSTITUTION.md::§7.2` and `CANONICAL_TRUTH_REGISTRY.md::tenant_identity_and_branding`:

### Brand color flow

```
data/org_config.json
   ↓ (HTTP)
GET /api/branding   (utils/api_branding.py, public endpoint)
   ↓
BrandingProvider (React)
   ↓ (sets CSS custom properties on :root)
--brand-primary, --brand-secondary, --brand-accent
   ↓ (consumed by)
shadcn primitives + Tailwind classes + StatCard accent stripes
```

### Tenant string rules

- **`frontend/web/src/**.tsx`** — zero tenant strings. No "Ecobank" anywhere. Use `useBranding()` hook (provider context) for tenant name display.
- **`pages/*.py`** — zero tenant strings. Use `utils/config.get_tenant_name()` etc.
- **`utils/**.py`\*\* (engines, managers) — zero tenant strings. Tenant context flows through config.
- **`data/org_config.json`** — tenant strings live HERE.

### Enforcement gates

- `gate_tenant_identity_hardcoding` (scripts/audit.py:20576) — bank-wide string scan
- `G381` — App.tsx contract literals preserved byte-for-byte
- `G382` — no hardcoded hex in `frontend/web/src/components/**.tsx` except `var(--brand-*)`

Severity: `CRITICAL`. Any tenant string violation blocks certification.

---

## Streamlit ↔ React parity rules

When the same domain is rendered in both Streamlit (legacy) and React (new):

1. **Both must show identical canonical data** — they read from the same engines
2. **Both must enforce the same RBAC** — same capabilities, same scope checks
3. **Differences are UX-only** — React uses shadcn primitives, Streamlit uses Streamlit widgets, but the data layer is identical
4. **No "Streamlit-only" features** — if a feature is canonical, it must be present in both (or planned for migration)
5. **No "React-only" canonical data** — until full migration, every canonical feature must work in Streamlit too

This is a _temporary_ constraint during transition. Once Streamlit is fully migrated (post v10.500), the constraint dissolves.

---

## Stage C frontend gates planned

| Gate                                   | Purpose                                                         | Severity        |
| -------------------------------------- | --------------------------------------------------------------- | --------------- |
| `gate_app_tsx_contract`                | App.tsx provider order + tenant strings                         | CRITICAL (G381) |
| `gate_no_hardcoded_hex_in_components`  | No hex in components except `var(--brand-*)`                    | HIGH (G382)     |
| `gate_token_index_css_sync`            | tokens.ts and index.css stay in sync (HSL components match hex) | HIGH            |
| `gate_react_no_role_string_comparison` | No `=== "Chief..."` etc. patterns                               | HIGH            |
| `gate_react_no_tenant_strings`         | No "Ecobank" or any tenant name                                 | CRITICAL        |
| `gate_useRole_hook_used`               | Verify components using role data go through useRole            | MEDIUM          |
| `gate_shadcn_primitive_purity`         | shadcn primitives not modified outside extensions               | HIGH            |
| `gate_streamlit_page_smoke`            | Every page passes smoke (existing `gate_page_smoke_test`)       | HIGH            |

---

## Open items

| ID    | Title                                                        | Resolution wave                                                    |
| ----- | ------------------------------------------------------------ | ------------------------------------------------------------------ |
| OI-9  | `/api/roles/me` endpoint contract                            | Resolved in this artifact; implementation in next governance batch |
| OI-13 | Full Streamlit page inventory + RBAC                         | Follow-up batch                                                    |
| OI-35 | Full enumeration of React `frontend/web/src/` tree           | Wave 4 amendment (Joshua to provide `dir /s /b`)                   |
| OI-36 | Router specification (React Router)                          | Wave 4 amendment                                                   |
| OI-37 | Documented A2Z extensions beyond Button.loading + Badge.tone | Stage C amendment as added                                         |
| OI-38 | useBranding() hook contract for tenant name display          | Wave 4 amendment                                                   |
| OI-59 | `seniorityTier: 0..6` field in useRole                       | Future batch — requires `_resolve_seniority_tier` in role_taxonomy |
| OI-60 | `capabilities: string[]` + `hasCapability(cap)` in useRole   | Future batch — requires `utils/rbac_matrix.py` (depends on OI-11)  |
| OI-61 | `isMD()` + `isChief()` convenience methods in useRole        | Future batch — depends on seniorityTier (OI-59) shipping first     |
| OI-62 | `displayName` field in whoami-detailed endpoint              | Future batch — coordinated backend + React contract change         |
| OI-63 | TanStack Query adoption for data-fetching hooks              | Future stack-wide migration arc                                    |

---

**End of FRONTEND_GOVERNANCE.md**
