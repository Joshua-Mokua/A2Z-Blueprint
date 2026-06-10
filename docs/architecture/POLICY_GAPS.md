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

**Status:** CLOSED (v10.501 Phase 2 Arc C Batch 4c)
**Surfaced during:** Phase 1 Batch 3d (gitignore review)
**Closed during:** Phase 2 Arc C Batch 4c via Path (B) accept-and-document

**Resolution:** Path (B) selected. The `.gitignore` entry for
`data/users.json` is preserved (so removal-then-`git add .` cannot
silently re-add it), but the comment block above the entry is
rewritten from the misleading "plaintext credentials — replaced by
hashed users in v10.497" to an honest explanation of why the
inconsistency is intentional and what discipline preserves it.

A new section "Intentionally-tracked credential data" is added to
`OPERATIONAL_PROTOCOL.md` codifying the rule (do NOT run `git rm
--cached data/users.json`), the trigger (any fresh-eyes session
proposing to fix the apparent inconsistency), the rationale (bootstrap
workflow not designed), and the future migration path to Path A
(when repo privacy posture changes).

**Operational risk profile unchanged:** the file's contents are
bcrypt-wrapped hashes (post-v10.497) and bcrypt-envelope-wrapped
SHA-256 hashes (post-v10.500 Batch 3c). The aggregate is still
sensitive but contains no plaintext credentials. Privacy is gated
on repo access scope, which is currently private.

**No regression test ships in this batch** because Path (B) makes
zero behavioural code changes — only doctrine and a `.gitignore`
comment edit. Adding a test that asserts "data/users.json is still
tracked in git" or "POLICY_GAPS.md says GAP-002 is CLOSED" would be
testing the test artifact itself, not behavior. The Batch 4a + 4b
regression suite (30/30) continues to protect the auth path.

**Bundled dev-dep fix:** `httpx>=0.27.0` added to
`requirements-dev.txt` after Batch 4b's regression test surfaced
the missing dependency on a fresh venv. Discovered too late to
include in Batch 4b; cleanly bundled here as a single-line dev-deps
edit that needs no separate batch.

---

## GAP-002 — (historical record preserved below)

**Status (historical, pre-closure):** OPEN
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

**Status:** CLOSED (v10.501 Phase 2 Arc B Batch 4b)
**Surfaced during:** Phase 1 Batch 3b inspection
**Closed during:** Phase 2 Arc B Batch 4b

**Resolution:** `slowapi` mounted on the FastAPI app via SlowAPIMiddleware
+ a custom 429 exception handler. Per-endpoint policy now enforced:

- `/api/auth/login` — 10 attempts per minute per IP + 100 per hour per IP
  (`@limiter.limit("10/minute;100/hour")`, keyed by remote address).
- `/api/auth/change-password` — 5 attempts per minute per bearer token
  (`@limiter.limit("5/minute", key_func=_ratelimit_key_by_token)`).
  Token-keyed rather than IP-keyed because NAT'd corporate networks
  would otherwise share a 5/min budget across hundreds of users.
- `/api/auth/whoami-detailed` — explicitly NOT decorated (legitimate
  dashboard polling).

429 responses additionally write an `API_RATE_LIMITED` audit row via
the custom `_ratelimit_exceeded_handler` in `utils/api.py`, with
path + method + IP + limit detail. The handler best-efforts the
authenticated username from the bearer token (where available) but
NEVER includes the raw JWT in the audit payload — pinned by
`test_429_handler_does_not_leak_token_in_audit`.

X-RateLimit-* response headers are intentionally disabled
(`headers_enabled=False`) to avoid leaking remaining-quota
information to brute-forcing attackers.

Regression coverage: `tests/test_rate_limit_auth.py` — 8 test cases
covering: per-IP 10/min on login (PASS up to 10, 429 on 11th), 429
response shape (Retry-After + JSON detail), credential non-leakage
in 429 body, per-token 5/min on change-password, per-token-vs-per-IP
independence (two tokens from the same host get separate buckets),
whoami-detailed unlimited (30 requests, zero 429s), audit row
written on 429, audit row does NOT contain the raw JWT.

**Operational constraint declared:** In-memory storage (slowapi's
default) is correct ONLY for single-worker FastAPI deployment.
Multi-worker would let an attacker's requests round-robin across
workers, each with its own counter. The single-worker constraint is
now codified in `OPERATIONAL_PROTOCOL.md` (introduced this batch).
Multi-worker scaling becomes a future arc gated on switching the
limiter storage backend to Redis or memcached.

---

## GAP-006 — (historical record preserved below)

**Status (historical, pre-closure):** OPEN
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

**Phase 2 Arc A (CLOSED, v10.501 Batch 4a, commit `e542acd`):**
GAP-001 and GAP-005 closed via shared `validate_password_policy`
helper + Streamlit `current_password` parity.

**Phase 2 Arc B (CLOSED, v10.501 Batch 4b, commit `97fb635`):**
GAP-006 closed via slowapi mount with per-IP login limit and
per-token change-password limit. Custom 429 handler writes audit
row; single-worker FastAPI declared as operational constraint in
`OPERATIONAL_PROTOCOL.md`.

**Phase 2 Arc C (CLOSED, v10.501 Batch 4c):** GAP-002 closed via
Path (B) accept-and-document. `.gitignore` comment rewritten;
new section "Intentionally-tracked credential data" added to
`OPERATIONAL_PROTOCOL.md`. Bundled dev-dep fix: `httpx>=0.27.0`
added to `requirements-dev.txt`.

**Phase 2 status: CLOSED.** 4 gaps closed across 3 arcs.
Net status of POLICY_GAPS at Phase 2 boundary: 1 OPEN (GAP-007 —
`_APP_VERSION` stamp policy), 2 DEFERRED (GAP-003 envelope
retirement, GAP-004 must_rotate token lifetime).

**Push to `origin/main` happens at this phase boundary** per
the established workflow (commit per batch, push at phase
boundaries).

**GAP-003 / GAP-004 remain DEFERRED** per original recommendations —
their triggers (observability data for GAP-003, established Phase 2
token discipline for GAP-004) have not materialised yet.

**GAP-007** is the only remaining OPEN item. The `_APP_VERSION`
stamping discipline was applied de facto across all three Phase 2
batches (bump per batch). A future hygiene arc could either codify
this as binding doctrine in `OPERATIONAL_PROTOCOL.md` (with an
audit gate enforcing the bump per batch) or formally deprecate
the stamp as informational. Either decision is small; not gating
any other work.
