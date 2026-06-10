# CHANGELOG_v10501_batch4a.md

**Batch:** v10.501 Phase 2 Arc A Batch 4a
**Date:** 2026-06-10
**Authors:** Joshua Mokua + Claude
**Closure:** GAP-001 (password complexity advertised but not enforced) + GAP-005 (Streamlit force_change_pw lacks current_password verify)
**Phase 1 → Phase 2 boundary commit:** `92c2e0a`
**Phase 2 Arc A status after this batch:** **CLOSED**

---

## Summary

Closes the first two `POLICY_GAPS.md` items by introducing a single
source of truth for the password policy and bringing Streamlit's
forced-rotation flow to parity with the FastAPI endpoint's defensive
divergence (Batch 3b).

The arc consists of one batch (this one). Five files modified, two
new files, one version bump.

---

## Files changed

### New files

| Path | Lines | Purpose |
|---|---:|---|
| `tests/test_validate_password_policy.py` | ~150 | 14 regression cases proving every policy rule, every named attacker-dictionary entry from GAP-001's risk paragraph, defensive non-string inputs, contract shape, and a SECURITY pin that the reason string never echoes the candidate password. |
| `docs/CHANGELOG_v10501_batch4a.md` | this file | Per-batch closure record. |

### Modified files

| Path | Change | Closes |
|---|---|---|
| `utils/core.py` | New module-level `validate_password_policy(pw) -> (ok, reason)` inserted before `class UserManager:`. Module constants `_PWD_MIN_LENGTH=8` and `_PWD_SPECIAL_CHARS` exposed. | GAP-001 (helper) |
| `utils/api.py` | `/api/auth/change-password` endpoint replaces length-only check with `validate_password_policy()` call. Deferred import of the helper alongside `UserManager`. Stale CGR1 comment refreshed. | GAP-001 (API) |
| `pages/_login.py` | Voluntary `change_pw` form (line 238) and `force_change_pw` form (line 317) both adopt the helper. `force_change_pw` gains `current_password` input + `um.authenticate()` verify + audit log on mismatch + new-equals-current rejection. | GAP-001 (Streamlit) + GAP-005 |
| `docs/architecture/POLICY_GAPS.md` | GAP-001 and GAP-005 flipped to CLOSED with closure summaries; historical OPEN/DEFERRED records preserved below the new status block per RL1. Phase summary updated. | doctrine sync |
| `docs/architecture/REVIVAL_LEDGER.md` | New top entry (this batch). | RL1 append discipline |
| `docs/continuity/SESSION_BOOTSTRAP.md` | Refreshed stale commit hashes (the Phase 1 section mislabelled `216171d` as Batch 3d — it is Batch 3c; actual Batch 3d is `f268330`; HEAD is `92c2e0a`). Phase 2 status section added. Active workstreams renumbered. | doctrine sync + drift-watchlist item #1 |
| `app.py` | `_APP_VERSION` bumped to `v10.501-batch4a-2026.06.10`. | session_state cache invalidation |

---

## The policy

Single function `validate_password_policy(pw: str) -> tuple[bool, str]`
in `utils/core.py`. Returns `(True, "")` on accept, `(False, reason)`
on reject. The reason string is suitable for direct display to end
users (`st.error`, FastAPI `HTTPException.detail`).

Rules enforced:

1. At least 8 characters.
2. Contains at least one uppercase letter (A–Z).
3. Contains at least one lowercase letter (a–z).
4. Contains at least one digit (0–9).
5. Contains at least one special character from `!@#$%^&*()_+-=[]{}|;:'",.<>/?` `~\\`.

These rules match what `utils/core.py:313` (the new-account email
template) has always advertised. Phase 2 Arc A's job was to close the
stated-vs-enforced gap, not to choose a new policy.

---

## Call sites

The helper is called from THREE places, all updated in this batch:

| Path | Line | Context |
|---|---:|---|
| `pages/_login.py` | 238 | Voluntary `change_pw` form — user changes their own password via the login screen |
| `pages/_login.py` | 317 | `force_change_pw` form — required password rotation on first login or after admin reset |
| `utils/api.py` | 501 | `/api/auth/change-password` endpoint — React frontend + any future API consumer |

Any future code path that sets a password MUST route through this
helper. The convention is now mechanical, not advisory.

---

## Operational notes

### Existing credentials are unaffected

The policy gates *new* passwords only. `verify_pw` is unchanged.
All 1438 existing bcrypt-backed and envelope-wrapped accounts
continue to authenticate with their current credentials.

### Synthetic credential convention conflicts with the new policy

The `EcoStaff<NNNN>` convention used by `generate_staff_v2.py` does
**not** meet the new policy (missing a special character). This means:

- **Existing synthetic users CAN still log in** — `verify_pw` is on
  the login path, not the change path. Their stored hash is checked
  against the entered password verbatim.
- **Existing synthetic users CANNOT set `EcoStaff<NNNN>` as a NEW
  password** — any forced or voluntary rotation will reject it.
- **Test flows that exercise password rotation must use a compliant
  string.** For example: `EcoStaff0001!` (the original plus a `!`)
  or `MyP@ssw0rd`.

If Phase 2+ decides to regenerate the synthetic credential set to
match the new policy, that becomes its own batch (and a small one
— one `generate_staff_v2.py` edit + a re-bootstrap of `users.json`).
Not in scope here.

### Backup-before-mutation: N/A for this batch

This batch makes zero writes to credential or audit data files
(`data/users.json`, `data/audit_log.json`). All changes are code,
tests, and doctrine. The backup-before-mutation discipline applies
to **scripts** that mutate state; nothing in this batch fits that
description.

---

## Verification performed during authoring

- `python -m py_compile` / `ast.parse` clean on all three modified
  Python files.
- `grep` confirmed zero `len(...) < 8` length-only checks remain on
  any password-change path.
- Helper smoke-tested against 14 representative inputs:

```
PASS: validate('Abcdef1!')      -> (True, '')         [minimal accept]
PASS: validate('EcoStaff0001!') -> (True, '')         [credential + special]
PASS: validate('MyP@ssw0rd')    -> (True, '')         [canonical example]
PASS: validate('Ab1!')          -> (False, 'too short')
PASS: validate('abcdef1!')      -> (False, 'no upper')
PASS: validate('ABCDEF1!')      -> (False, 'no lower')
PASS: validate('Abcdefgh!')     -> (False, 'no digit')
PASS: validate('Abcdefg1')      -> (False, 'no special')
PASS: validate('password')      -> (False, 'no upper')     ← GAP-001 risk
PASS: validate('12345678')      -> (False, 'no upper')     ← GAP-001 risk
PASS: validate('Password1')     -> (False, 'no special')   ← GAP-001 risk
PASS: validate('')              -> (False, 'too short')
PASS: validate(None)            -> (False, 'must be string')
PASS: validate(12345678)        -> (False, 'must be string')
```

14/14 green.

---

## Operator extraction instructions

The delivery is a ZIP whose root contains `_batch4a_payload/` per
Trap #14. Inside `_batch4a_payload/` the tree mirrors the destination:

```
_batch4a_payload/
  app.py
  utils/
    core.py
    api.py
  pages/
    _login.py
  tests/
    test_validate_password_policy.py
  docs/
    architecture/
      POLICY_GAPS.md
      REVIVAL_LEDGER.md
    continuity/
      SESSION_BOOTSTRAP.md
    CHANGELOG_v10501_batch4a.md
```

From the repo root (`C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\`),
with `.venv\Scripts\activate` active, run (in order):

```cmd
:: Verify the staging folder exists and is namespaced correctly
dir _batch4a_payload

:: Code files
copy /Y _batch4a_payload\app.py                                                app.py
copy /Y _batch4a_payload\utils\core.py                                          utils\core.py
copy /Y _batch4a_payload\utils\api.py                                           utils\api.py
copy /Y _batch4a_payload\pages\_login.py                                        pages\_login.py
copy /Y _batch4a_payload\tests\test_validate_password_policy.py                 tests\test_validate_password_policy.py

:: Doctrine artifacts
copy /Y _batch4a_payload\docs\architecture\POLICY_GAPS.md                       docs\architecture\POLICY_GAPS.md
copy /Y _batch4a_payload\docs\architecture\REVIVAL_LEDGER.md                    docs\architecture\REVIVAL_LEDGER.md
copy /Y _batch4a_payload\docs\continuity\SESSION_BOOTSTRAP.md                   docs\continuity\SESSION_BOOTSTRAP.md
copy /Y _batch4a_payload\docs\CHANGELOG_v10501_batch4a.md                       docs\CHANGELOG_v10501_batch4a.md

:: Remove staging folder ONLY AFTER all copies completed
rmdir /S /Q _batch4a_payload
```

### Verification steps

```cmd
:: 1. Syntax check on modified Python files
python -m py_compile utils\core.py utils\api.py pages\_login.py

:: 2. Run the new regression test (pytest required; install if missing)
python -m pytest tests\test_validate_password_policy.py -v

:: 3. Confirm helper is present and call sites are wired
findstr /n "validate_password_policy" utils\core.py utils\api.py pages\_login.py

:: 4. Confirm no length-only checks remain
findstr /n /c:"len(req.new_password)" utils\api.py
findstr /n /c:"len(cp_new) < 8" pages\_login.py
findstr /n /c:"len(fp_new) < 8" pages\_login.py
:: All three should return zero matches.

:: 5. Confirm _APP_VERSION bump
findstr /n "_APP_VERSION" app.py
```

Expected results:
- Step 1: silent success (no syntax errors).
- Step 2: 14 tests pass. If a test is missing dependencies, install
  pytest in the venv: `pip install pytest`.
- Step 3: one line for `utils/core.py` (definition), one for
  `utils/api.py` (deferred import + call), two for `pages/_login.py`
  (import + two call sites).
- Step 4: all three findstr calls return zero matches.
- Step 5: `_APP_VERSION = "v10.501-batch4a-2026.06.10"`.

### Commit

```cmd
git add app.py utils\core.py utils\api.py pages\_login.py tests\test_validate_password_policy.py docs\architecture\POLICY_GAPS.md docs\architecture\REVIVAL_LEDGER.md docs\continuity\SESSION_BOOTSTRAP.md docs\CHANGELOG_v10501_batch4a.md
git status
git commit -m "v10.501 Phase 2 Arc A Batch 4a - password policy hardening (closes GAP-001 + GAP-005)

Introduces validate_password_policy(pw) -> (ok, reason) in utils/core.py
as the single source of truth for the password policy advertised in
utils/core.py:313 (uppercase + lowercase + digit + special + min 8).

Three call sites adopt the helper:
- pages/_login.py voluntary change_pw form
- pages/_login.py force_change_pw form
- utils/api.py /api/auth/change-password endpoint

force_change_pw additionally gains a current_password input field and
verify call, bringing Streamlit to parity with FastAPI's defensive
divergence (Batch 3b convention). Closes GAP-005.

Regression coverage: tests/test_validate_password_policy.py (14 cases
including every rule, every named attacker-dictionary entry from
GAP-001's risk paragraph, defensive non-string inputs, contract shape,
and a SECURITY pin that the reason string never echoes the candidate
password).

Doctrine updates:
- POLICY_GAPS.md: GAP-001 + GAP-005 flipped to CLOSED with closure
  summaries (historical OPEN/DEFERRED records preserved per RL1)
- REVIVAL_LEDGER.md: new top entry per RL1 append discipline
- SESSION_BOOTSTRAP.md: stale commit hashes refreshed
  (216171d was mislabelled as Batch 3d; corrected to Batch 3c;
   actual Batch 3d is f268330; HEAD is 92c2e0a)
- CHANGELOG_v10501_batch4a.md NEW

Operational note: the policy gates NEW passwords only. verify_pw is
unchanged; all 1438 existing accounts continue to authenticate with
their current credentials. The synthetic EcoStaff<NNNN> convention
does not meet the new policy (no special character) and so cannot be
used as a NEW password during testing — compliant test strings like
EcoStaff0001! must be used for rotation flows.

Phase 2 Arc A CLOSED. Arc B (rate limiting, GAP-006) is next focus."
```

Push to `origin/main` is deferred to the Phase 2 phase boundary per
the established workflow (commit per batch, push at phase
boundaries).

---

## What did NOT change

- `utils/core.py::UserManager.change_password` — still just hashes and
  saves. Validation lives at call sites by design (input validation
  is a presentation concern; the model layer trusts its inputs).
- `utils/core.py::UserManager.verify_pw` — unchanged. The policy is
  forward-only; existing credentials are not retroactively invalidated.
- `utils/core.py::UserManager.authenticate` — unchanged.
- `utils/auth_jwt.py` — unchanged. Token lifetime, scope semantics,
  and dependencies are out of scope for Arc A.
- `frontend/web/src/` — unchanged. The React `/change-password` page
  will receive policy reason strings from the FastAPI endpoint as
  `HTTPException.detail`; existing error-handling renders them as-is.
  Phase 2+ could add client-side preview validation (mirror the policy
  in TypeScript) for better UX, but that's a separate batch.

---

## Next batch

**v10.501 Phase 2 Arc B Batch 4b — API rate limiting (closes GAP-006).**

Reference model: Streamlit's existing 5-attempts-then-15-min lockout
at `pages/_login.py:194-204`. Persistence: in-memory `slowapi`,
single-worker FastAPI declared as operational constraint in
`OPERATIONAL_PROTOCOL.md`. Target endpoints: `/api/auth/login`
(10/min/IP, 100/hr), `/api/auth/change-password` (5/min/token).
Whoami-detailed unlimited (legitimate dashboard polling).

Expected: 2–3 sub-batches (4b dependency + middleware mount, 4c
per-endpoint config + tests, optional 4d telemetry).
