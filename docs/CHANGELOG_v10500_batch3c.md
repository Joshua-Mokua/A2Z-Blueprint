# CHANGELOG — v10.500 Phase 1 Batch 3c

**Date:** 2026-05-26
**Predecessor commit:** `2aab56b` (v10.500 Phase 1 Batch 3b)
**Doctrine framing:** *metabolism stabilization* — legacy credential tissue gets converted into modern tissue, no cosmetic surgery, no immune-system redesign.

---

## Summary

Closes Phase 1 closure gate **#8** — dormant SHA-256 migration path. Adds the envelope verification path to `UserManager.verify_pw`, instruments the previously-silent auto-upgrade failure path with full-traceback logging, and ships `scripts/verify_bcrypt.py` as the one-shot bulk migration tool for dormant accounts.

Phase 1 closure status after this batch: **9/10 gates green**. Only Batch 3d (doctrine refresh) remains.

---

## Doctrine notes

**Envelope is TRANSITIONAL stabilization, NOT canonical end-state.** The bcrypt-wrapped-SHA-256 form is an accepted technical bridge to get every account onto bcrypt-backed storage without requiring plaintext password recovery. Phase 2 hardening may decide on forced normalization to direct bcrypt, Argon2 migration, passwordless strategies, or SSO integration. Batch 3c does not classify envelope as architectural doctrine.

**No schema marker.** Envelope-wrapped and direct-bcrypt hashes are indistinguishable at-rest — both use the `$2b$/$2a$/$2y$` prefix. This is deliberate:
- avoids users.json schema drift,
- keeps the at-rest representation simple,
- preserves operational reversibility,
- makes the migration invisible to end users.

Envelope population is tracked at *runtime* via the new INFO log in `verify_pw`, not at-rest.

**Auto-conversion of envelope → direct bcrypt on login deferred to Phase 2.** Adding opportunistic re-hashing in `authenticate` introduces another state transition, harder forensic reasoning, and a "auth succeeded but migration partially failed" branch. Phase 2 can add staged normalization with observable counters, dashboards, audit trail events, and ratchet deadlines. Batch 3c keeps envelope stable indefinitely.

**Silent-swallow instrumentation goes deep.** The `authenticate()` auto-upgrade swallow (which masked a `NameError` for ~2 years before Batch 3b's hotfix surfaced it) now logs username + exception class + full traceback. Auth availability remains primary — failures still don't re-raise — but migration hygiene is now observable. Banking posture: log enough for postmortems, log nothing that compromises secrets.

**Security boundary** — neither `verify_pw`'s new log nor `scripts/verify_bcrypt.py` ever prints: plaintext password, sha256 hex, bcrypt string, tokens, or stack locals containing auth material. Username + log message + exception type only. Sample usernames are advisory in script output (count-first formatting).

---

## Files

| # | Path | Action | Lines (approx) |
|---|---|---|---|
| 1 | `utils/core.py` | MODIFY (surgical) | +imports logger, ~95 line rewrite of verify_pw + authenticate |
| 2 | `scripts/verify_bcrypt.py` | NEW | ~290 lines |
| 3 | `docs/CHANGELOG_v10500_batch3c.md` | NEW | this file |

3 files total. No frontend changes.

---

## Architectural contracts established

**`verify_pw(pw, stored, username="")`** — three paths tried in order:

1. **Direct bcrypt** — `bcrypt.checkpw(pw, stored)` when `stored` starts with `$2b$`/`$2a$`/`$2y$`. Produced by `hash_pw`, `change_password`, `add_user`, or successful auto-upgrade.
2. **Envelope bcrypt** — `bcrypt.checkpw(sha256(pw).hex, stored)`. Produced by the migration script wrapping legacy SHA-256 hashes.
3. **Legacy SHA-256 direct** — `sha256(pw).hex == stored`. Unchanged from pre-bcrypt era; only reached when stored field is a 64-char hex value.

Each bcrypt check costs ~25ms; worst case (envelope-stored, wrong password) is ~50ms. Operationally irrelevant at this scale.

**`$2y$` prefix support added.** Python's `bcrypt` emits `$2b$` but external systems may produce `$2y$` (semantically equivalent — same algorithm, different version tag). Three places updated: `verify_pw` (path 1), `authenticate` (auto-upgrade detection), `scripts/verify_bcrypt.py` (`classify_hash`).

**`authenticate` instrumentation:**
```python
except Exception as e:
    logger.error(
        "Auto-upgrade SHA-256 -> bcrypt FAILED for user '%s': "
        "%s: %s — auth allowed, migration deferred",
        username, type(e).__name__, e,
        exc_info=True,
    )
```
Auth result is unchanged (`return True, u`); only observability changes.

**`verify_pw` envelope-success log:**
```python
logger.info(
    "Envelope-backed credential authenticated for user '%s'", username
)
```
Fires ONLY on the envelope path (path 2). Direct bcrypt success (path 1, the steady-state) is intentionally silent to keep log volume sane. Future ratchet planning can compute "envelope users still authenticating" from these INFO lines.

---

## scripts/verify_bcrypt.py — operational contract

**Audit-only by default:**
```cmd
python -m scripts.verify_bcrypt
```
Prints hash distribution. Reports total users, direct-bcrypt count, legacy-SHA-256 count, empty count, malformed count, plus sample usernames per bucket (advisory). Never modifies anything.

**Upgrade with dry-run + confirmation prompt:**
```cmd
python -m scripts.verify_bcrypt --upgrade
```
Audits, prints plan, prompts `Proceed? [y/N]`, then writes wrapped hashes via atomic temp-file + rename. Re-audits to confirm zero legacy SHA-256 remain.

**Automation mode** (skips prompt):
```cmd
python -m scripts.verify_bcrypt --upgrade --yes
```

**Planning mode** (never writes, even with `--yes`):
```cmd
python -m scripts.verify_bcrypt --upgrade --dry-run
```

**Exit codes:**
- 0 — audit complete OR upgrade applied OR dry-run complete
- 1 — confirmation declined
- 2 — users.json not found / unreadable
- 3 — users.json malformed JSON
- 4 — bcrypt module unavailable (required for `--upgrade`)
- 5 — internal write error

Idempotent — re-running `--upgrade` after a clean migration prints "Nothing to do" and exits 0.

---

## Out of scope (deferred)

- **Opportunistic envelope → direct bcrypt upgrade on successful login** — Phase 2 hardening (see doctrine notes above).
- **Argon2 migration / passwordless / SSO** — Phase 2.
- **Migration-event audit log entries** (`API_AUDIT_BCRYPT_MIGRATED` etc.) — Phase 2; current scope uses logger.info, not audit_log.
- **Ratchet deadline enforcement** — Phase 2.
- **Voluntary password-change UI in React** — out of scope across all of Phase 1.

---

## Phase 1 closure status after this batch

| Gate | Status |
|---|---|
| 1. Real user opens app | ✅ 3a |
| 2. Redirect to /login | ✅ 3a |
| 3. Authenticate | ✅ 3a |
| 4. Receive token | ✅ 3a |
| 5. Refresh page, stay authenticated | ✅ 3a |
| 6. Access protected routes | ✅ 3a |
| 7. Logout cleanly | ✅ 3a |
| 8. Dormant SHA-256 migration path | ✅ **shipped in 3c** |
| 9. must_change_password consistent Streamlit + FastAPI | ✅ 3b |
| 10. Doctrine artifacts refreshed | ⏳ Batch 3d |

---

## Operator verification checklist

Backend running (`python -m utils.api`).

**Path A — script audit on current users.json:**

1. `python -m scripts.verify_bcrypt`
2. Expected: prints hash distribution. Most users likely still SHA-256 (since hash_pw was broken until commit 2aab56b). Some recent logins or change_password calls (e.g. william001 after Batch 3b verification) should show as direct bcrypt.

**Path B — dry-run upgrade:**

3. `python -m scripts.verify_bcrypt --upgrade --dry-run`
4. Expected: same audit output, plus PLAN line showing eligible count, plus "--dry-run set — NO changes will be written."
5. Verify `data/users.json` unchanged (e.g. `git diff data/users.json` — should be unchanged from any pre-existing diff).

**Path C — actual upgrade with prompt:**

6. `python -m scripts.verify_bcrypt --upgrade`
7. Plan displayed; prompt `Proceed? [y/N]`. Type `y` and Enter.
8. Expected: writes file, re-audits, reports zero legacy SHA-256 remain, "Migration complete."
9. Verify the final audit shows all direct-bcrypt counts + empty + malformed only.

**Path D — idempotency verification:**

10. `python -m scripts.verify_bcrypt --upgrade --yes`
11. Expected: "Nothing to do — no legacy SHA-256 hashes found."

**Path E — login-path regression check** (envelope auth works end-to-end):

12. Flag a previously-SHA-256 user for re-login (or use any non-william001 staff). Sign in via React `/login` with their original password (e.g. `EcoStaff` + last-4-of-staff-code).
13. Expected: login succeeds. Backend logs (FastAPI terminal) should show:
    ```
    INFO  a2z.core  Envelope-backed credential authenticated for user '<username>'
    ```
14. F5 → stays authenticated (token persistence).

**Path F — auto-upgrade-failure instrumentation** (synthetic test):

15. This path is informational — no real failure expected post-fix. If `authenticate()` ever fails its auto-upgrade in the future, the log should now show:
    ```
    ERROR  a2z.core  Auto-upgrade SHA-256 -> bcrypt FAILED for user '<name>': <ExceptionType>: <msg>
    Traceback (most recent call last):
      ...
    ```
    instead of silent failure.

**Path G — Streamlit regression check:**

16. Open Streamlit at `http://localhost:8501`, sign in with a now-envelope-wrapped user. Login should still succeed — `UserManager.verify_pw` is shared between FastAPI and Streamlit and handles all three paths.

---

## Rollback discipline

Single atomic commit. If verification fails:

```cmd
git checkout -- utils/core.py
del scripts\verify_bcrypt.py
del docs\CHANGELOG_v10500_batch3c.md
```

If the upgrade has been applied and you want to roll BACK the data:
```cmd
:: Manual: identify which users were upgraded from the logger.info output,
:: then re-set their password fields from a previous git-tracked users.json
:: snapshot. There is no automated downgrade — envelope is fail-forward.
```

In practice, the safer rollback for a bad upgrade is to **forward-fix**: have affected users go through the standard `must_change_password` rotation flow (Batch 3b mechanism). The migration is reversible in *behavior* even if not in stored bytes.

---

## Next batch

**Batch 3d** — doctrine reconciliation. Refresh `docs/continuity/SESSION_BOOTSTRAP.md`, write `REVIVAL_LEDGER` entries for 3a/3b/3c, classify in `GOVERNANCE_REALITY_INDEX`, record the *stated-vs-enforced password policy gap* (Batch 3b finding), record the *Trap #14 namespaced-staging-folder protocol*, `.gitignore` review for `data/audit_log.json` + `data/audit_trail.jsonl`. Closes Phase 1 closure gate #10.

After 3d: Phase 1 substrate is complete and the locally-committed batches (3a/3b/3c/3d) can be pushed to origin as a single coherent arc.

---

**End of CHANGELOG — v10.500 Phase 1 Batch 3c**
