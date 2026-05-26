# CHANGELOG — v10.500 Phase 1 Batch 3b

**Date:** 2026-05-26
**Predecessor commit:** `13d5258` (v10.500 Phase 1 Batch 3a)
**Doctrine in force:** CGR1 (reality-grounding), Traps #11 (no fabrication), #12 (no paste cascade), #13 (proposed — no raw secret material in chat/doctrine)

---

## Summary

Extends Phase 1 auth with FastAPI-side `must_change_password` enforcement, matching what Streamlit has done since `pages/_login.py`. Adds the `must_rotate` token scope to `utils/auth_jwt.py` — a JWT scope claim that gates every existing authenticated endpoint mechanically, allowing only `POST /api/auth/change-password` to accept the scoped token. Adds the React `ChangePassword` page and a path-aware `ProtectedRoute` gate that confines `must_rotate` users to `/change-password` until rotation completes.

Closes Phase 1 closure gate **#9** (must_change_password consistent across Streamlit + FastAPI). Gates 8 (dormant migration) and 10 (doctrine refresh) remain for Batches 3c and 3d.

---

## CGR1 doctrine notes

**Password policy match.** The stated policy in `core.py:313` (new-account email) advertises "at least 8 characters and include uppercase, lowercase, a number, and a special character." The *enforced* policy in `pages/_login.py:286-291` (Streamlit force_change_pw) is **length ≥ 8 only**. CGR1 says reality wins over doctrine. Batch 3b matches the enforced policy in the new FastAPI endpoint so the two platforms agree mechanically. The stated/enforced gap is flagged for Batch 3d doctrine review or a future Phase 2 hardening arc.

**Defensive divergence from Streamlit.** The new `POST /api/auth/change-password` endpoint **requires `current_password` verification** even during forced rotations. Streamlit's `force_change_pw` flow does not. The API gate is stricter because a stolen `must_rotate`-scope token would otherwise let an attacker set an arbitrary new password. Dormant accounts migrated in Batch 3c (envelope approach) will retain their original passwords intact, so they can provide current_password. Streamlit's gap is recorded for Phase 2 hardening.

**Identity is RoleProvider's authority.** The ChangePassword page does NOT display the username, because RoleProvider deliberately does not hydrate identity during `must_rotate` (whoami-detailed would 403 the must_rotate token). Generic "Set a new password to continue" keeps separation-of-concerns clean: AuthProvider owns the token, RoleProvider owns identity, neither bleeds.

---

## Files

| # | Path | Action | Lines (approx.) |
|---|---|---|---|
| 1 | `utils/auth_jwt.py` | MODIFY | full rewrite — scope constants, scope param on create_access_token, new `_extract_token_payload` helper, `get_current_user_allow_rotation` dep |
| 2 | `utils/api.py` | MODIFY (surgical) | TokenResponse extended, ChangePasswordRequest added, login route teaches scope contract, new `/api/auth/change-password` endpoint (+152 lines) |
| 3 | `frontend/web/src/types/auth.ts` | MODIFY | TokenResponse + AuthStatus + AuthContextValue extended; ChangePasswordRequest added |
| 4 | `frontend/web/src/providers/AuthProvider.tsx` | MODIFY | must_rotate status handling, changePassword action, third localStorage key |
| 5 | `frontend/web/src/components/ProtectedRoute.tsx` | MODIFY | path-aware must_rotate gate (confines to /change-password) |
| 6 | `frontend/web/src/pages/Login.tsx` | MODIFY | redirect must_rotate users to /change-password |
| 7 | `frontend/web/src/pages/ChangePassword.tsx` | NEW | rotation form composing existing primitives |
| 8 | `frontend/web/src/App.tsx` | MODIFY | /change-password route registered |
| 9 | `docs/CHANGELOG_v10500_batch3b.md` | NEW | this file |

---

## Architectural contracts established by this batch

**Token scopes** (`utils/auth_jwt.py`):
- `TOKEN_SCOPE_FULL = "full"` — default; granted to normally-authenticated users. Encoded WITHOUT a `scope` claim (backward compat with pre-3b tokens).
- `TOKEN_SCOPE_MUST_ROTATE = "must_rotate"` — granted when `must_change_password=true`. Encoded WITH a `scope` claim. Only accepted by `get_current_user_allow_rotation`.

**Backward compatibility:** pre-Batch-3b tokens currently in client localStorage have NO scope claim. They are interpreted as full-scope on decode. Existing sessions survive the deploy without forced re-login.

**Endpoint gates:**
- `Depends(get_current_user)` — full scope only. Rejects must_rotate with 403. **All existing endpoints inherit this for free.**
- `Depends(require_admin)` — chains through get_current_user; inherits the rotation gate.
- `Depends(require_role(...))` — chains through get_current_user; inherits the rotation gate.
- `Depends(get_current_user_allow_rotation)` — accepts BOTH scopes. **Only `/api/auth/change-password` uses this dep.** Hardcoded by convention; reviewers should flag any other endpoint that adopts it.

**Login response shape** (extended):
```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "expires_in_seconds": 1800,
  "username": "william001",
  "role": "Chief Executive & Managing Director",
  "must_change_password": false       // NEW in Batch 3b
}
```

**ChangePassword response shape** (same as login response, with `must_change_password=false` and a fresh full-scope `access_token`).

**Audit events emitted:**
- `API_LOGIN_FORCE_PW` — login succeeded but must_rotate-scope token was issued
- `API_PASSWORD_CHANGE_SUCCESS` — rotation completed; detail includes `forced=true|false`
- `API_PASSWORD_CHANGE_FAILED` — any rejection (current_password mismatch, length, equality, persistence). Detail captures reason.

Existing `API_LOGIN_SUCCESS` continues to fire for non-rotating logins. Audit-log scheme is unchanged.

**Frontend state machine** (extended):
```
initializing
    ├── unauthenticated  ───── login() w/o flag ────→ authenticated
    │                          login() w/ flag  ────→ must_rotate
    │
    ├── authenticated    ───── logout()          ────→ unauthenticated
    │                          401 from any req  ────→ expired
    │
    ├── must_rotate      ───── changePassword()  ────→ authenticated
    │                          logout()          ────→ unauthenticated
    │                          401 from rotation ────→ expired
    │
    └── expired          ───── login() success   ────→ authenticated (or must_rotate)
```

**Storage keys** (third one added):
```
localStorage['a2z_token']             — JWT string
localStorage['a2z_token_expires_at']  — ms-since-epoch as string
localStorage['a2z_must_rotate']       — 'true' when token is must_rotate-scope (Batch 3b)
```

---

## What is explicitly out of scope (deferred)

- **Password complexity rules** — length-only matches Streamlit; strengthening to upper/lower/digit/special would need parallel Streamlit update for consistency. Out of scope for this batch.
- **Streamlit current-password verification** — would harden the Streamlit force_change_pw flow to match FastAPI's defensive divergence. Phase 2 hardening item.
- **Voluntary password-change UI in React** — the page and endpoint support it, but no entry point is shipped. Future settings page work.
- **Token blocklist after rotation** — JWT is stateless. The old full-scope token (issued when the user originally got admin access pre-flag-set) does not get revoked by rotation. Not exploitable in this batch's flow (users get must_rotate first), but worth documenting. Future hardening.

---

## Phase 1 closure status after this batch

| Gate | Status |
|---|---|
| 1. Real user opens app | ✅ shipped in 3a |
| 2. Redirect to /login | ✅ shipped in 3a |
| 3. Authenticate | ✅ shipped in 3a |
| 4. Receive token | ✅ shipped in 3a |
| 5. Refresh page, stay authenticated | ✅ shipped in 3a |
| 6. Access protected routes | ✅ shipped in 3a |
| 7. Logout cleanly | ✅ shipped in 3a |
| 8. Dormant SHA-256 migration path | ⏳ Batch 3c |
| 9. `must_change_password` consistent Streamlit + FastAPI | ✅ shipped in 3b |
| 10. Doctrine artifacts refreshed | ⏳ Batch 3d |

8/10 gates green after this batch.

---

## Operator verification checklist

Backend must be running (`python -m utils.api` on port 8502) and Vite must be running (`npm run dev` in `frontend/web/`).

**Path A — Existing user who does NOT have must_change_password set** (e.g., `william001`):

1. Visit `http://localhost:5173/` → redirect to `/login`
2. Sign in as `william001 / ECOStaff001`
3. **Expected:** redirect to `/` (Dashboard renders). Same behavior as Batch 3a.
4. Network tab: `/api/auth/login` response body should include `"must_change_password": false`
5. localStorage should NOT have `a2z_must_rotate` key (or it should be cleared if previously set).

**Path B — Forced rotation flow** (you need a user with `must_change_password=true`):

To set up a test user with the flag:
```cmd
cd "C:\Users\Joshua\Desktop\A2Z Blue Print\a2z"
.venv\Scripts\activate.bat
python -c "import json; p='data/users.json'; d=json.load(open(p)); u='admin'; d[u]['must_change_password']=True; json.dump(d, open(p,'w'), indent=2); print(f'Set must_change_password=True for {u}')"
```

Then in browser (after clearing localStorage and hard-refreshing):

6. Visit `/login` → sign in as `admin / ECOStaff001`
7. **Expected:** redirect to `/change-password` (NOT to `/`). The rotation banner shows "🔑 You must set a new password before you can access the system."
8. Network tab: login response body should include `"must_change_password": true`. localStorage should now have `a2z_must_rotate: "true"`.
9. Try to manually navigate to `/` by typing the URL → **redirected back to `/change-password`** (frontend gate working).
10. Open a new browser tab and `curl -H "Authorization: Bearer <token-from-localStorage>" http://localhost:8502/api/auth/whoami-detailed`. **Expected: 403 with detail "Password rotation required..."** (backend gate working — mechanical enforcement, not advisory).
11. In the `/change-password` form:
    - Submit empty fields → "Enter your current password."
    - Submit short new password (e.g., "abc") → "New password must be at least 8 characters."
    - Submit new = current → "New password must differ from your current password."
    - Submit non-matching confirm → "Confirmation does not match the new password."
    - Submit wrong current_password → "Current password is incorrect."
12. Submit `current_password=ECOStaff001`, `new_password=NewSecure2026`, `confirm=NewSecure2026`
13. **Expected:** redirect to `/` (Dashboard renders, identity hydrates). localStorage: `a2z_must_rotate` is removed; `a2z_token` has a fresh value.
14. Network tab: `/api/auth/change-password` returned 200 with `"must_change_password": false` in response body. Subsequent `/api/auth/whoami-detailed` returned 200 (token now full-scope).
15. F5 → stay on Dashboard.

**Path C — Backend audit verification:**

16. Check `data/audit_log.json` (or wherever audit_log writes). Expected entries from the test:
    - `API_LOGIN_FORCE_PW` (after step 6 login)
    - `API_PASSWORD_CHANGE_SUCCESS` with `forced=true` (after step 12)
    - `API_AUTH_WHOAMI_DETAILED` (after step 13's hydration)

**Path D — Streamlit parity check** (ensure we didn't break the existing Streamlit force_change_pw flow):

17. Reset the admin flag: `python -c "import json; p='data/users.json'; d=json.load(open(p)); d['admin']['must_change_password']=True; json.dump(d, open(p,'w'), indent=2)"`
18. Visit Streamlit at `http://localhost:8501`
19. Sign in as admin → Streamlit should still show its own force_change_pw form. Streamlit flow unchanged.

If all 19 verification points pass, **Phase 1 gate #9 is closed**.

---

## TypeScript / build verification

```cmd
cd frontend\web
npx tsc --noEmit
```

Expected: same 3 pre-existing errors in `Card.tsx` and `Input.tsx`. Zero errors in any Batch 3b file.

```cmd
:: Backend syntax sanity
cd "C:\Users\Joshua\Desktop\A2Z Blue Print\a2z"
python -c "import ast; ast.parse(open('utils/auth_jwt.py').read()); ast.parse(open('utils/api.py').read()); print('Both Python files parse cleanly')"
```

---

## Rollback discipline

This batch is a single atomic commit. If verification fails:

1. Do not commit.
2. Frontend: `git checkout -- frontend/web/src/`
3. Backend: `git checkout -- utils/`
4. Surface the failure mode for diagnostic re-evaluation.

The 9 files form a cohesive unit — backend scope plumbing, frontend state machine extension, new page, and route registration. Partial application leaves half-states (e.g., backend issues must_rotate tokens but frontend doesn't recognize the flag).

After local verification, restart the FastAPI backend (`python -m utils.api`) to pick up the modified `auth_jwt.py` and `api.py`. Vite HMR will pick up frontend changes automatically.

---

## Next batch

**Batch 3c** — bcrypt migration tooling. Implements the envelope approach (`bcrypt(sha256(existing_hash))`), adds `$2y$` prefix support to `verify_pw`, instruments the silent auto-upgrade-on-login failure path with logging, and ships `scripts/verify_bcrypt.py` for one-shot dormant-account migration. Pure backend; no frontend changes. Closes Phase 1 gate #8.

Then:
- **Batch 3d** — doctrine hygiene: SESSION_BOOTSTRAP refresh, REVIVAL_LEDGER entries for 3a/3b/3c, GOVERNANCE_REALITY_INDEX classification, Phase 1 closure marker, the stated/enforced password policy gap recorded as a Phase 2 hardening item, `data/audit_log.json` and `data/audit_trail.jsonl` `.gitignore` review.

---

**End of CHANGELOG — v10.500 Phase 1 Batch 3b**
