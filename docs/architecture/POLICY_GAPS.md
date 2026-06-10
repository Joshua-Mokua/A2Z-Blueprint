# POLICY_GAPS.md

**Status:** ACTIVE
**Introduced:** v10.500 Phase 1 Batch 3d (2026-05-26)
**Authority:** Constitutional Article CGR1 (`SYSTEM_CONSTITUTION.md`)
**Maintainer:** Operator (Joshua) + Claude
**Companion artifacts:** `GOVERNANCE_REALITY_INDEX.md`, `OPERATIONAL_PROTOCOL.md`

---

## Purpose

Records intentional gaps between **stated policy** (what doctrine, UI
copy, or email templates advertise) and **enforced policy** (what code
actually mechanically enforces). Per CGR1, divergence between
documented intent and runtime reality is itself a tracked artifact.

Each entry has:
- **Gap:** the divergence statement
- **Stated location:** where the stronger policy appears in code/docs
- **Enforced location:** where the weaker policy actually runs
- **Risk:** what the gap exposes
- **Phase 2 recommendation:** closing approach
- **Status:** OPEN / DEFERRED / CLOSED

This is **not** an aspirational wishlist — it's a list of known
intentional divergences that future work should consider closing.

---

## GAP-001 — Password complexity advertised but not enforced

**Status:** CLOSED (v10.501 Phase 2 Batch 4a)
**Surfaced during:** Phase 1 Batch 3b (FastAPI `/api/auth/change-password`
endpoint design)
**Closed during:** Phase 2 Arc A Batch 4a (commit pending — pushed at
Arc A phase boundary per OPERATIONAL_PROTOCOL)

**Resolution:** Introduced `validate_password_policy(pw) -> (ok, reason)`
in `utils/core.py` as the single source of truth for the policy
(uppercase + lowercase + digit + special + min 8). Three call sites
now share it:

- `pages/_login.py` voluntary `change_pw` form (line 238)
- `pages/_login.py` `force_change_pw` form (line 317)
- `utils/api.py` `/api/auth/change-password` endpoint (line 501)

Regression coverage: `tests/test_validate_password_policy.py` — 14
test cases including every rule (positive + negative), every
attacker-dictionary entry named in this gap's original risk paragraph
(`password`, `12345678`, `Password1`, etc.), empty/non-string defensive
cases, and a SECURITY pin that the reason string never echoes the
candidate password.

**Operational note on existing credentials:** the policy gates *new*
passwords only — `verify_pw` is unchanged, so the 1438 existing
bcrypt-backed and envelope-wrapped accounts continue to authenticate
with their current credentials. The synthetic `EcoStaff<NNNN>`
convention does not meet the new policy and would be rejected if
proposed as a *new* password during testing; test scenarios that
involve setting a fresh password must use a compliant string (e.g.
`EcoStaff0001!`).

---

## GAP-001 — (historical record preserved below)

**Status (historical, pre-closure):** OPEN
**Surfaced during:** Phase 1 Batch 3b (FastAPI `/api/auth/change-password`
endpoint design)

**Gap:** Doctrine and UI copy advertise a strong password policy
(uppercase + lowercase + digit + special character, minimum 8). Code
enforces length-only (minimum 8).

**Stated location:**
- `utils/core.py:313` — new-account email template:
  > *"Your new password must be at least 8 characters and include
  > uppercase, lowercase, a number, and a special character."*

**Enforced location:**
- `pages/_login.py:286-291` — Streamlit `force_change_pw` flow:
  ```python
  if fp_new != fp_confirm:
      st.error("Passwords do not match.")
  elif len(fp_new) < 8:
      st.error("Password must be at least 8 characters.")
  # No complexity check
  ```
- `utils/api.py` `/api/auth/change-password` (Batch 3b) — same
  length-only policy, deliberately mirroring Streamlit's actual behavior
  for cross-transport consistency (CGR1: match reality, not stated
  intent).

**Risk:** Users selecting weak passwords (e.g. `password`, `12345678`,
`aaaaaaaa`) pass validation. Banking auth threat model assumes attackers
will brute-force; weak passwords reduce the time-to-compromise on
intercepted records.

**Phase 2 recommendation:** Strengthen both Streamlit and FastAPI to
enforce the stated complexity rules in parallel. Avoid asymmetric
strengthening (one transport stronger than the other) — that creates
a UX gap that drives users to the weaker entry point.

Suggested implementation: introduce `validate_password_policy(pw: str)
-> tuple[bool, str]` helper in `utils/core.py` returning
`(ok, reason)`, called from BOTH Streamlit `_login.py` and FastAPI
`/api/auth/change-password`. Single source of truth for the policy.

---

## GAP-002 — `data/users.json` is gitignored but tracked

**Status:** OPEN
**Surfaced during:** Phase 1 Batch 3d (gitignore review)

**Gap:** `.gitignore` lists `data/users.json` as ignored, but the file
is tracked in git history. `git rm --cached data/users.json` would
fully untrack it, but doing so requires a bootstrap-from-generator
workflow that hasn't been designed.

**Stated location:** `.gitignore:38` — comment says
"Auth seeds (plaintext credentials — replaced by hashed users in
v10.497)".

**Enforced location:** `data/users.json` exists in working tree AND
in git index. Modifications continue to appear in `git status`.

**Risk:** Sensitive credential data (now bcrypt-wrapped, but still
sensitive in aggregate) continues to be versioned. New clones inherit
the credential blob via repo history. Privacy/access scope of the
repo determines actual exposure level.

**Phase 2 recommendation:** Either:
- **(A) Bootstrap-from-generator workflow.** `git rm --cached data/users.json`
  + ensure `generate_staff_v2.py` is a first-run prerequisite documented
  in README. New clones run the generator before starting the app.
  Operator's existing user records would need a separate sync mechanism
  (e.g., manual `users.json` from a secure source on first deploy).
- **(B) Accept the tracking and document.** Add an explicit comment to
  `.gitignore` clarifying the entry only applies to files NOT yet
  tracked, and that the existing tracked copy is intentional. Less
  hygienic but matches operational reality.

(A) is more correct; (B) is faster. Choose based on the security
posture Phase 2 wants for the repo.

---

## GAP-003 — Envelope verify path is permanent without retirement criteria

**Status:** DEFERRED (intentional per CGR1)
**Surfaced during:** Phase 1 Batch 3c (envelope migration design)

**Gap:** `UserManager.verify_pw` tries direct bcrypt → envelope bcrypt
→ legacy SHA-256. The envelope path exists indefinitely; there is no
mechanism to retire it once the envelope-wrapped user population
shrinks to zero.

**Stated location:** Batch 3c CHANGELOG and Batch 3d
`SESSION_BOOTSTRAP.md` describe envelope as a TRANSITIONAL stabilization
layer.

**Enforced location:** `utils/core.py:5783-5808` (verify_pw) — envelope
path runs unconditionally.

**Risk:** The envelope path adds ~25ms per failed direct-bcrypt verify.
At scale this is operationally irrelevant, but it represents code
that will eventually need removal. Without retirement criteria, the
envelope branch becomes permanent technical debt.

**Phase 2 recommendation:** Define retirement trigger via the
`Envelope-backed credential authenticated` INFO log:

- Phase 2 ships log aggregation / metrics dashboard for that log
- When the log fires for fewer than N users per month, signal that
  envelope population is approaching zero
- After 30 consecutive days of zero envelope log emissions, the
  envelope branch can be removed from `verify_pw` and the remaining
  paths simplified to (direct bcrypt → legacy SHA-256 fallback)
- Final retirement: remove SHA-256 fallback too, leaving direct-bcrypt-only

The observability hook (the INFO log) is in place. The metric collection
mechanism is Phase 2 work.

---

## GAP-004 — `must_rotate` tokens have no inactivity timeout shorter than full tokens

**Status:** DEFERRED
**Surfaced during:** Phase 1 Batch 3b (must_rotate scope design)

**Gap:** `must_rotate`-scope tokens have the same 30-minute lifetime
as full-scope tokens. A user who gets a `must_rotate` token and walks
away from the keyboard has 30 minutes before the token expires. During
that window, the token is only useful for `/api/auth/change-password`,
but it IS still a valid auth credential bound to the user account.

**Stated location:** `utils/auth_jwt.py:52` — `TOKEN_LIFETIME =
timedelta(minutes=30)` (single constant for all scopes).

**Enforced location:** same.

**Risk:** A shoulder-surfer could observe a `must_rotate` token in
DevTools and use it within the 30-minute window to set the user's
password. Threat model is narrow (requires physical/screen access
during the rotation window) but real.

**Phase 2 recommendation:** Reduce `must_rotate` token lifetime to
5-10 minutes. Implementation: factor `TOKEN_LIFETIME` into
`TOKEN_LIFETIME_FULL` (30 min) vs `TOKEN_LIFETIME_MUST_ROTATE` (5-10
min). One additional constant + one branch in `create_access_token`.

This is a small hardening; depth-of-defense rather than primary control.

---

## GAP-005 — Streamlit `force_change_pw` flow does not require current password

**Status:** CLOSED (v10.501 Phase 2 Batch 4a)
**Surfaced during:** Phase 1 Batch 3b
**Closed during:** Phase 2 Arc A Batch 4a

**Resolution:** `pages/_login.py` `force_change_pw` form now requires a
`Current password` input field and verifies it via
`um.authenticate(_fc_user, fp_current)` before applying the change.
Streamlit is now at parity with FastAPI's stricter behaviour
(introduced in Batch 3b). Failed-current-password attempts are
audit-logged as `PASSWORD_CHANGE_FAILED` with reason
`current_password mismatch (force_change_pw)`. The same form also
adopts `validate_password_policy` (GAP-001 closure) and rejects
new-equals-current (matching the FastAPI endpoint contract).

---

## GAP-005 — (historical record preserved below)

**Status (historical, pre-closure):** DEFERRED (defensive divergence already in place on API)
**Surfaced during:** Phase 1 Batch 3b

**Gap:** Streamlit's forced-rotation flow at `pages/_login.py::elif
mode == "force_change_pw"` asks for `new` and `confirm_new` only —
NOT `current`. A user who knows only the username and has a must_rotate
session can set any new password without proving knowledge of the
current credential.

**Stated location:** (none — the gap is in code only)

**Enforced location:** `pages/_login.py:283-291`.

**Defensive divergence already in place:** Batch 3b's
`/api/auth/change-password` endpoint DOES require `current_password`,
even on forced rotations. The API path is stricter than Streamlit.
This is intentional — the API is the more reachable threat surface.

**Risk:** Within Streamlit only. A user who has a Streamlit
`force_change_pw` session active can set any new password.

**Phase 2 recommendation:** Bring Streamlit into parity with FastAPI
by requiring `current_password` in `force_change_pw`. Single new
input field in the Streamlit form + `um.verify_pw(current, stored)`
check before `um.change_password()`. Minimal surface change.

---

## GAP-006 — No rate limiting on auth endpoints

**Status:** OPEN
**Surfaced during:** Phase 1 Batch 3b inspection

**Gap:** `/api/auth/login`, `/api/auth/change-password`, and
`/api/auth/whoami-detailed` have no rate limiting. Audit logging
catches failed attempts (`API_LOGIN_FAILED`, `API_PASSWORD_CHANGE_FAILED`)
but does not throttle.

**Risk:** Brute-force attacks against the auth endpoints are
slowed only by bcrypt's CPU cost (~25ms per check). With 1438
users in the system, an attacker could attempt ~40 logins/second per
attacker thread, multiplied across distributed attackers.

**Phase 2 recommendation:** Add per-IP rate limiting to auth endpoints.
FastAPI integrates well with `slowapi` or similar. Suggested limits:
- `/api/auth/login` — 10 attempts per minute per IP, 100 per hour
- `/api/auth/change-password` — 5 attempts per minute per token
- `/api/auth/whoami-detailed` — no limit (legitimate dashboard polling)

Streamlit already has a 5-attempts-then-15-minute-lockout mechanism
at `pages/_login.py:194-198`. The API has nothing equivalent.

---

## GAP-007 — `_APP_VERSION` stamp is informational only

**Status:** DEFERRED
**Surfaced during:** Phase 1 Batch 3d

**Gap:** `app.py::_APP_VERSION` is updated manually per batch but not
mechanically enforced or checked. Drift between the stamp and actual
shipped state is undetected.

**Phase 2 recommendation:** Decide whether `_APP_VERSION` is doctrine
(updated per batch, audit-gate-enforced) or convenience (informational).
Pick one and codify in `OPERATIONAL_PROTOCOL.md`.

---

## Phase-by-phase status summary

**Phase 1 (closed, v10.500 commit f268330 / HEAD 92c2e0a):** 7 gaps
recorded. 0 closed at Phase 1 boundary. 5 OPEN, 2 DEFERRED.

**Phase 2 Arc A (CLOSED, v10.501 Batch 4a):** GAP-001 and GAP-005
closed via shared `validate_password_policy` helper + Streamlit
`current_password` parity. Net status: 3 OPEN, 2 DEFERRED.

**Phase 2 Arc B (next):** GAP-006 (rate limiting). Planned per
SESSION_BOOTSTRAP. Persistence strategy: in-memory `slowapi`,
single-worker FastAPI declared as operational constraint in
`OPERATIONAL_PROTOCOL.md` when Arc B lands.

**Phase 2 Arc C (after Arc B):** GAP-002 (`users.json` tracking) —
direction (B) accept-and-document selected. Single-batch arc.

**GAP-003 / GAP-004 / GAP-007 remain DEFERRED** per original
recommendations — their triggers (observability data, established
Phase 2 token discipline, OPERATIONAL_PROTOCOL section) have not
materialised yet.
