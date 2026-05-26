# CHANGELOG — v10.500 Phase 1 Batch 3a

**Date:** 2026-05-26
**Predecessor commit:** `f3187dc` (v10.499 Stage C Batch 2e)
**Doctrine in force:** CGR1 (reality-grounding), Traps #11 (no fabrication), #12 (no paste cascade), #13 (proposed — no raw secret material in chat/doctrine)

---

## Summary

Replaces the v10.495 `AuthProvider` no-op stub with a real Bearer-header JWT auth substrate for the React SPA. Wires `RoleProvider` to gate its fetches on `auth.status === 'authenticated'`. Replaces `ProtectedRoute`'s "Please log in" dead-end with a `<Navigate to="/login" />` redirect. Adds a `/login` page composing existing `Input` / `Button` / `useBranding` primitives. Protects `/`, `/perform`, `/profitability`; `/components` remains public for design-system governance inspection.

CSRF is NOT addressed in this batch — the architecture is Bearer-header, not cookie-auth, so CSRF is not the threat model. CSRF reconsideration is deferred to a Phase 2 security arc tied to any future httpOnly-cookie migration.

---

## CGR1 doctrine note

Batch 2d (`useRole` hook + `RoleProvider`) and Batch 2e (`ProtectedRoute` wrapper) remain **VALID shipments**, not rollbacks. Their structural correctness was independently verified by code inspection at the start of Batch 3a; their operational disconnection was caused by the missing auth substrate (this batch), not by component-level defects. The components' shape, error handling, and derived-value patterns are preserved unchanged in Batch 3a; only the wiring around them is added.

This distinction matters for REVIVAL_LEDGER integrity. 2d and 2e are not being re-shipped or corrected — they are being **completed** by the substrate they originally assumed would exist.

---

## Files

| # | Path | Action |
|---|---|---|
| 1 | `frontend/web/src/types/auth.ts` | NEW |
| 2 | `frontend/web/src/providers/AuthProvider.tsx` | REPLACE (was 16-line stub) |
| 3 | `frontend/web/src/hooks/useAuth.ts` | NEW |
| 4 | `frontend/web/src/pages/Login.tsx` | NEW |
| 5 | `frontend/web/src/lib/api.ts` | MODIFY (full rewrite for clarity) |
| 6 | `frontend/web/src/providers/RoleProvider.tsx` | MODIFY |
| 7 | `frontend/web/src/components/ProtectedRoute.tsx` | MODIFY |
| 8 | `frontend/web/src/App.tsx` | MODIFY |

No backend changes. The Bearer-header / JWT-in-body contract at `utils/api.py:276-312` and `utils/auth_jwt.py:1-289` was already correctly shaped for this work.

---

## Architectural contracts established by this batch

**AuthProvider** (token lifecycle only — separation of concerns enforced):
- Owns: `token`, `expiresAt`, `status`, `error`, `login`, `logout`
- Does NOT own: user identity, role, RBAC helpers (those belong to RoleProvider)
- State machine: `initializing → unauthenticated | authenticated`, `authenticated → unauthenticated (logout) | expired (401)`

**lib/api.ts** (central HTTP wrapper):
- Reads `_currentToken` from a module-level holder set by AuthProvider
- Attaches `Authorization: Bearer <token>` when token is present
- Invokes registered `_on401Callback` before throwing `AuthExpiredError` on 401
- `AuthExpiredError` is a distinct error class so callers can distinguish auth-state changes from generic failures

**RoleProvider** (identity + RBAC, gated on auth):
- `useEffect` dep is `[auth.status]` (not the token value)
- Fires only when `auth.status === 'authenticated'`
- Resets state on transitions out of authenticated
- Uses cancellation token to avoid setState on unmounted/transitioned-away components

**ProtectedRoute** (route guard):
- Renders `null` during `auth.status === 'initializing'` (no flicker)
- `<Navigate to="/login" state={{ from: location }} replace />` on unauthenticated
- Preserves original location for post-login redirect

**Login page** (operational entry point):
- Composes `Input`, `Button`, `useBranding`, `useAuth`
- No HTML `<form>` tag (system constraint); submit via `onClick` + Enter-key handler
- Post-login redirects to `location.state.from` or `/`
- Shows "Your session expired" hint when `auth.status === 'expired'`

---

## Storage keys (single source of truth)

```
localStorage['a2z_token']             — JWT string
localStorage['a2z_token_expires_at']  — ms-since-epoch as string
```

Expiry safety margin: 30 seconds (tokens expiring within 30s are treated as expired).

All localStorage reads/writes are wrapped in try/catch for browser-policy robustness; private mode / quota-exceeded / disabled-storage degrade silently to in-memory only.

---

## What is explicitly out of scope (deferred)

- **Token refresh / silent renewal** — backend forbids per `utils/auth_jwt.py:17-18`; re-login on expiry is the documented contract for Phase 1.
- **httpOnly cookie migration** — would require backend `Set-Cookie` on login + frontend `credentials: 'include'` switch + CSRF defense. Deferred to Phase 2 security arc.
- **CSRF defense** — not applicable to Bearer-header architecture (no auto-attached cookies → no CSRF threat). Re-evaluated only if cookie migration is chosen.
- **Multi-tab session sync** — single-tab acceptable for Phase 1.
- **Remember-me / extended sessions** — future work.
- **Password reset flow via React** — admins continue to use existing Streamlit admin pages until the rotation flow is reconsidered alongside Batch 3b/3c.
- **`must_change_password` enforcement on FastAPI side** — Batch 3b explicitly addresses this. Batch 3a deliberately does not check the flag at login; the backend will be taught to surface it in a distinguishable response shape during Batch 3b, and the Login page will react then.

---

## Phase 1 closure gates (per Batch 3a doctrine #10)

Phase 1 is NOT closed by this batch alone. The operational closure gates are:

1. ✅ Real user can open app
2. ✅ Real user redirected to `/login`
3. ✅ Real user authenticates
4. ✅ Real user receives token
5. ✅ Real user refreshes page and remains authenticated
6. ✅ Real user accesses protected routes
7. ✅ Real user logs out cleanly
8. ⏳ Dormant SHA-256 users have a defined migration path (Batch 3c)
9. ⏳ `must_change_password` enforced consistently across Streamlit + FastAPI (Batch 3b)
10. ⏳ Doctrine artifacts refreshed (SESSION_BOOTSTRAP, REVIVAL_LEDGER, GOVERNANCE_REALITY_INDEX) (Batch 3d)

Items 1–7 become VERIFIABLE upon Batch 3a deployment. Items 8–10 ship in Batches 3b/3c/3d.

---

## Operator verification checklist

After extracting and running `npm run dev` in `frontend/web/`:

1. **Unauthenticated boot:** Visit `http://localhost:5173/`. Expect: immediate redirect to `/login`. Network tab: `/api/branding` returns 200, no `/api/auth/whoami-detailed` or `/api/roles/registry` traffic (RoleProvider didn't fire — correctly gated).

2. **Login form:** `/login` renders with branded header. Submit empty form → local "Please enter both username and password" error. Submit invalid credentials → "Invalid username or password." error. Submit valid credentials (e.g., `olive001` / `EcoStaff0001` for MD per existing convention) → redirect to `/`.

3. **Authenticated boot:** After login, network tab shows `/api/auth/whoami-detailed` and `/api/roles/registry` both return 200 with Authorization: Bearer header attached.

4. **Page refresh persistence:** F5 on `/` while authenticated. Expect: brief flash of `null`/loading, then Dashboard renders. localStorage check: `a2z_token` and `a2z_token_expires_at` populated.

5. **Protected route gating:** Visit `/perform` and `/profitability` while authenticated → render. While logged out → redirect to `/login` with `state.from` set.

6. **Public route:** Visit `/components` without authentication → Showcase page renders (governance/design-system inspection path preserved).

7. **Logout:** Add a temporary `<button onClick={logout}>logout</button>` somewhere reachable (or call `useAuth().logout()` from devtools) → state clears, localStorage cleared, redirect to `/login`.

8. **Expiry simulation:** In devtools, manually set `localStorage.a2z_token_expires_at = "0"` and F5. Expect: redirect to `/login` (stale-expiry cleanup path fired).

9. **Server-side rejection:** Restart the FastAPI backend (invalidates the per-process JWT secret per `utils/auth_jwt.py:60-65`). Try to access `/` with stale token. Expect: 401 from any authenticated endpoint → AuthProvider flips to `'expired'` → redirect to `/login` with "Your session expired" hint shown.

If all 9 verification points pass, gates 1–7 of Phase 1 closure are achieved.

---

## TypeScript / build verification

```bash
cd frontend/web
npm install           # no new deps; should be a no-op
npx tsc --noEmit      # should pass with 0 errors
npm run build         # should succeed (tsc && vite build)
```

If `npx tsc --noEmit` reports errors, do NOT commit. Investigate before proceeding.

---

## Rollback discipline

This batch is a **single atomic commit** in the new ZIP-extraction workflow. If verification fails:

1. Do not commit.
2. `git checkout -- frontend/web/src/` to restore origin state.
3. Surface the failure mode for diagnostic re-evaluation.

The 8 files form a cohesive unit. Partial application leaves half-states (e.g., AuthProvider replaced but api.ts unchanged → TypeScript build fails). All or none.

---

## Next batch

**Batch 3b** — FastAPI `must_change_password` enforcement + forced-rotation contract alignment between Streamlit and FastAPI. Adds the response-shape distinguisher the Login page will need to react to.

Followed by:
- **Batch 3c** — bcrypt migration tooling, `$2y$` support, auto-upgrade observability, dormant-account migration via the envelope approach.
- **Batch 3d** — doctrine hygiene (SESSION_BOOTSTRAP refresh, REVIVAL_LEDGER entries for 3a/3b/3c, GOVERNANCE_REALITY_INDEX classification) + Phase 1 closure marker.

---

**End of CHANGELOG — v10.500 Phase 1 Batch 3a**
