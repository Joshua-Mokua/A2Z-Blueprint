# CHANGELOG_v10501_batch4c.md

**Batch:** v10.501 Phase 2 Arc C Batch 4c
**Date:** 2026-06-10
**Authors:** Joshua Mokua + Claude
**Closure:** GAP-002 (`data/users.json` is gitignored but tracked) via Path (B) accept-and-document
**Bundled fix:** `httpx>=0.27.0` added to `requirements-dev.txt`
**Previous batch commit:** `97fb635` (v10.501 Phase 2 Arc B Batch 4b)
**Phase 2 status after this batch:** **CLOSED** — push to origin scheduled at the phase boundary

---

## Summary

Closes GAP-002 by replacing the misleading `.gitignore` comment on
the `data/users.json` entry with an honest explanation of the
intentional inconsistency, and codifying the rule (do NOT run
`git rm --cached data/users.json`) in `OPERATIONAL_PROTOCOL.md`.

The arc is one batch. Zero behavioural code changes. No new tests.

Bundled fix: `httpx>=0.27.0` added to `requirements-dev.txt` — a
band-aid Joshua applied manually during Batch 4b verification is
now the canonical source.

---

## Files changed

### New files

| Path | Lines | Purpose |
|---|---:|---|
| `docs/CHANGELOG_v10501_batch4c.md` | this file | Per-batch closure record. |

### Modified files

| Path | Change | Closes |
|---|---|---|
| `.gitignore` | Replaced the misleading "Auth seeds (plaintext credentials...)" comment on the `data/users.json` entry with a 28-line comment block honestly explaining: contents are bcrypt-wrapped (not plaintext), the entry exists to prevent silent re-add via `git add .`, the file is still tracked because the bootstrap-from-generator workflow (Path A) hasn't been designed. Pointer to OPERATIONAL_PROTOCOL.md. The entry itself (`data/users.json`) is unchanged. | GAP-002 (Path B) |
| `requirements-dev.txt` | `httpx>=0.27.0` added to the Testing block with an inline comment explaining why (`fastapi.TestClient` defers httpx import, raises at use-site if missing). | Bundled fix from Batch 4b verification gap |
| `docs/architecture/OPERATIONAL_PROTOCOL.md` | New section "Intentionally-tracked credential data" inserted before the "Single-worker FastAPI operational constraint" section (Batch 4b). | doctrine codification |
| `docs/architecture/POLICY_GAPS.md` | GAP-002 flipped to CLOSED with Path B closure summary; historical OPEN record preserved per RL1. Phase summary substantially rewritten — Phase 2 is now CLOSED with 4 gaps closed across 3 arcs. | doctrine sync |
| `docs/architecture/REVIVAL_LEDGER.md` | New top entry (this batch). | RL1 append discipline |
| `docs/continuity/SESSION_BOOTSTRAP.md` | Phase 2 status → CLOSED. Phase 2 commit list extended with Batch 4c row. Active workstreams renumbered — Stage C governance enforcement resumption is the natural next focus. Known doctrine gaps section refreshed (4 closures, 1 OPEN, 2 DEFERRED). | doctrine sync |
| `app.py` | `_APP_VERSION` bumped to `v10.501-batch4c-2026.06.10`. | session_state invalidation |

---

## The honest `.gitignore` story

Before Batch 4c, `.gitignore` line 51 said:

```
# Auth seeds (plaintext credentials — replaced by hashed users in v10.497)
data/users.json
```

This was wrong on two counts:

1. **"Plaintext credentials"** — false since v10.497. The file is
   bcrypt-wrapped (`UserManager.hash_pw`). Post-v10.500 Batch 3c, 1437
   previously-SHA-256 hashes are wrapped in bcrypt envelopes via
   `scripts/verify_bcrypt.py`. Plaintext credentials are not present.

2. **The entry without explanation** — anyone seeing the entry in
   `.gitignore` would reasonably conclude the file should be
   un-tracked via `git rm --cached`. POLICY_GAPS GAP-002 explicitly
   flagged this drift trap. Without explanation, the next operator
   or Claude session would have "fixed" it and broken the bootstrap.

Batch 4c replaces the comment with a 28-line block that:

- States that the file is INTENTIONALLY TRACKED.
- Explains contents are bcrypt-wrapped, not plaintext.
- Explains why the entry exists (prevent silent re-add via
  `git add .` if the file is ever removed).
- Explains why it's still tracked (bootstrap-from-generator workflow
  not designed).
- Names the operational discipline (do NOT run `git rm --cached`).
- Points to OPERATIONAL_PROTOCOL.md for the codified rule.

The `data/users.json` entry itself is unchanged. The discipline is
the same; the documentation matches reality.

---

## Why no regression test in this batch

Path B makes zero behavioural code changes — just a `.gitignore`
comment edit, a dev-deps line addition, and four doctrine documents.
A test asserting "data/users.json is still tracked in git" would be
testing a git operation, not application behavior. A test asserting
"POLICY_GAPS.md says GAP-002 is CLOSED" would be testing the test
artifact itself.

The Batch 4a + 4b regression suite (30 cases) continues to protect
the actual auth surface. Running it after extraction is the
verification gate for this batch — if those tests still pass, Batch
4c hasn't broken anything.

---

## Operator extraction instructions

The delivery is a ZIP whose root contains `_batch4c_payload/` per
Trap #14. Tree:

```
_batch4c_payload/
  .gitignore
  app.py
  requirements-dev.txt
  docs/
    architecture/
      OPERATIONAL_PROTOCOL.md
      POLICY_GAPS.md
      REVIVAL_LEDGER.md
    continuity/
      SESSION_BOOTSTRAP.md
    CHANGELOG_v10501_batch4c.md
```

### Step 1 — Extract the ZIP at the repo root

If you extracted via the Windows GUI (open ZIP → Extract All), the
staging folder `_batch4c_payload\` should now exist at the repo root.
Verify with:

```cmd
dir _batch4c_payload
```

You should see `app.py`, `requirements-dev.txt`, `docs\`, and a
`.gitignore` file. If the GUI extraction stripped hidden/dotfiles,
re-extract with PowerShell:

```cmd
powershell -Command "Expand-Archive -Path batch4c_payload.zip -DestinationPath . -Force"
dir _batch4c_payload /A
```

(`/A` shows hidden + dotfiles.)

### Step 2 — Copy the 8 files into place

These are the REAL commands. Each one starts with `copy /Y`. If you
see anything starting with `::` those are cmd comments and they do
nothing — skip them.

```cmd
copy /Y _batch4c_payload\.gitignore .gitignore
copy /Y _batch4c_payload\app.py app.py
copy /Y _batch4c_payload\requirements-dev.txt requirements-dev.txt
copy /Y _batch4c_payload\docs\architecture\OPERATIONAL_PROTOCOL.md docs\architecture\OPERATIONAL_PROTOCOL.md
copy /Y _batch4c_payload\docs\architecture\POLICY_GAPS.md docs\architecture\POLICY_GAPS.md
copy /Y _batch4c_payload\docs\architecture\REVIVAL_LEDGER.md docs\architecture\REVIVAL_LEDGER.md
copy /Y _batch4c_payload\docs\continuity\SESSION_BOOTSTRAP.md docs\continuity\SESSION_BOOTSTRAP.md
copy /Y _batch4c_payload\docs\CHANGELOG_v10501_batch4c.md docs\CHANGELOG_v10501_batch4c.md
```

Expect `1 file(s) copied.` eight times.

### Step 3 — Sync dev dependencies

```cmd
pip install -r requirements-dev.txt
```

Look for `Requirement already satisfied: httpx>=0.27.0` (you have
it from the Batch 4b verification) or a fresh `Successfully
installed httpx-...`.

### Step 4 — Run the full regression suite

```cmd
python -m pytest tests\test_validate_password_policy.py tests\test_rate_limit_auth.py -v
```

Expect **30 passed**. If anything fails, stop and report — Batch 4c
should be code-behavior-neutral.

### Step 5 — Verify the `.gitignore` comment landed correctly

```cmd
findstr /n "INTENTIONALLY TRACKED" .gitignore
```

Expect one match (the new comment header). If zero matches, the new
`.gitignore` didn't land — re-run the copy step.

```cmd
findstr /n "Auth seeds.plaintext credentials" .gitignore
```

Expect ZERO matches. If you still see the old comment, the new
`.gitignore` didn't land.

### Step 6 — Clean up staging

```cmd
rmdir /S /Q _batch4c_payload
```

### Step 7 — Stage and commit

```cmd
git add .gitignore app.py requirements-dev.txt docs\architecture\OPERATIONAL_PROTOCOL.md docs\architecture\POLICY_GAPS.md docs\architecture\REVIVAL_LEDGER.md docs\continuity\SESSION_BOOTSTRAP.md docs\CHANGELOG_v10501_batch4c.md
git status
```

Expect 1 new file + 7 modified files staged. The two `docs/`
untracked items (`KPA Pin.pdf`, `architecture/survey_inputs/`) should
still be untracked and excluded from the commit.

```cmd
git commit -m "v10.501 Phase 2 Arc C Batch 4c - users.json tracking via Path B (closes GAP-002); PHASE 2 CLOSED"
```

### Step 8 — Push to origin (PHASE 2 BOUNDARY)

This is the moment the established workflow allows the push. Three
Phase 2 commits land at origin in one operation:

```cmd
git log origin/main..HEAD --oneline
```

Expect three lines:
- `[hash4c] v10.501 Phase 2 Arc C Batch 4c ...`
- `97fb635 v10.501 Phase 2 Arc B Batch 4b ...`
- `e542acd v10.501 Phase 2 Arc A Batch 4a ...`

If you see those three (and only those three) ahead of `origin/main`,
push:

```cmd
git push origin main
```

If you see additional commits not authored by Phase 2 batches, stop
and investigate — something unrelated landed locally and needs
its own decision (commit message audit, separate push, etc.).

---

## Phase 2 closure summary

**4 gaps closed across 3 arcs:**

| Gap | Closed in | Mechanism |
|---|---|---|
| GAP-001 — password complexity advertised but not enforced | Batch 4a (`e542acd`) | `validate_password_policy(pw)` helper + 3 call sites |
| GAP-005 — Streamlit force_change_pw lacks current_password verify | Batch 4a (`e542acd`) | Streamlit form field + `um.authenticate()` verify |
| GAP-006 — no rate limiting on auth endpoints | Batch 4b (`97fb635`) | slowapi mount + per-IP login + per-token change-password |
| GAP-002 — `data/users.json` tracked-but-gitignored | Batch 4c (this batch) | `.gitignore` comment rewrite + OPERATIONAL_PROTOCOL section |

**Regression suite:** 30/30 green across Batches 4a + 4b. Batch 4c
ships no new tests because zero behavioural code changes.

**Doctrine additions to OPERATIONAL_PROTOCOL.md during Phase 2:**

1. Single-worker FastAPI operational constraint (Batch 4b) —
   binding rule that protects the rate-limit storage model.
2. Intentionally-tracked credential data (Batch 4c) — binding rule
   that prevents the `.gitignore` "fix" trap.

**Net POLICY_GAPS status at Phase 2 boundary:**
- 4 CLOSED (GAP-001, GAP-002, GAP-005, GAP-006)
- 1 OPEN (GAP-007 — `_APP_VERSION` stamp policy)
- 2 DEFERRED (GAP-003 envelope retirement, GAP-004 must_rotate lifetime)

**Next focus:** Stage C governance enforcement resumes per
SESSION_BOOTSTRAP. ~30 gates remaining (OI-66). Doctrine surface is
healthy; OPERATIONAL_PROTOCOL grew two binding rules during Phase 2.
The work pattern (ZIP → copy → pytest → commit) is now well-rehearsed.

---

## What did NOT change

- **`data/users.json` content.** No mutation in this batch.
  Backup-before-mutation discipline N/A.
- **`utils/api.py`, `utils/core.py`, `pages/_login.py`.** Unchanged
  from their post-Batch-4b state. Phase 2 Arc C is doctrine and
  configuration only.
- **`frontend/web/src/`.** Unchanged.
- **The `data/users.json` `.gitignore` ENTRY itself.** Only the
  comment above it was rewritten.

---

## Post-Phase-2 watchlist (non-blocking)

Worth deciding before the next major batch, none are blockers:

1. **FastAPI `@app.on_event("startup")` → lifespan handler.**
   Emits a DeprecationWarning on every test run and every API
   startup. Pre-dates Phase 2. Small hygiene arc.

2. **GAP-007 `_APP_VERSION` stamp policy.** The three Phase 2
   batches all bumped the stamp per batch. Decide whether to make
   this audit-gate-enforced doctrine or formally classify as
   informational and accept the de facto pattern.

3. **`docs/KPA Pin.pdf` and `docs/architecture/survey_inputs/`.**
   Untracked items that survived Phase 2 unchanged. Decide whether
   to gitignore, commit, or delete.

4. **Envelope INFO log observability.** GAP-003 retirement criteria
   need log aggregation infrastructure that doesn't exist yet. Not
   urgent; tracked as DEFERRED.

5. **`must_rotate` token lifetime.** GAP-004 asks for a separate
   shorter lifetime for `must_rotate` tokens (5-10 min) vs full
   (30 min). Defence-in-depth, not primary control. Tracked as
   DEFERRED.
