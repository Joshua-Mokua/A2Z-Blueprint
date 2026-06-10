# OPERATIONAL_PROTOCOL.md

**Status:** ACTIVE
**Introduced:** v10.500 Phase 1 Batch 3d (2026-05-26)
**Authority:** Constitutional Article CGR1 (`SYSTEM_CONSTITUTION.md`)
**Maintainer:** Operator (Joshua) + Claude
**Companion artifact:** `REVIVAL_LEDGER.md`, `GOVERNANCE_REALITY_INDEX.md`

---

## Purpose

Codifies the operational discipline that emerged during Phase 1 (v10.500
Batches 3a–3d). These are not architectural decisions; they are
**process protocols** for how operator and Claude work together on
multi-batch arcs, what mistakes to avoid, and what safety nets to keep
in place.

Each protocol is named (Trap #N or by mechanism) and has a defined
trigger condition. Violations are recoverable but cost real time and
trust.

---

## Trap #11 — No fabrication

**Rule:** Every claim about file contents, line numbers, function
signatures, or runtime behavior must be grounded in same-turn code
inspection. Claude does not assert "the function does X" from memory
when the question matters; Claude inspects.

**Trigger:** Any claim that would change a batch's design, scope, or
verification plan.

**Mechanism:** Inspect → ground claim → cite inspected lines. Use the
`view` and `bash_tool` (grep) tools.

**Codified during:** Stage C Batch 2c-meta (commit `184ffd1`).
**Reinforced by:** the architectural re-evaluation at the start of
Batch 3a (which caught 8 errors in the original Phase 1 prose spec),
the credential drift in Batch 3b (where the userMemory's stated
password convention propagated wrong into the transcript summary; the
fix was inspecting `generate_staff_v2.py` line 481 instead of trusting
memory), and the verify_pw observability gap in Batch 3c (where the
test "passed" because we tested the wrong user, not because the log
fired).

---

## Trap #12 — No paste cascade

**Rule:** Multi-file deliveries are packaged as ZIP archives, not
posted inline as a sequence of code blocks. Inline paste at scale
fragments operator attention, encourages copy-paste errors, and bloats
chat context.

**Trigger:** Any delivery touching more than ~3 files OR a single file
larger than ~200 lines.

**Mechanism:**
1. Claude writes all files to a staging area in its sandbox
2. ZIP the staging area
3. `present_files` the ZIP to the operator
4. Operator extracts, applies via explicit `copy`/`xcopy` commands,
   verifies, and commits

**Codified during:** Stage C Batch 2c-meta (commit `184ffd1`).
**Refined during:** Batch 3a (full ZIP workflow with extraction
instructions), Batch 3b (added explicit backup-of-modified-file
pattern in deliveries), Batch 3c (introduced operator-confirmation
prompts in mutation scripts).

---

## Trap #14 — No path-colliding extractions

**Rule:** When packaging a ZIP delivery whose contents target an
existing directory in the destination tree, the ZIP MUST place those
files under a uniquely-named staging folder (e.g., `_batch3c_payload/`)
that cannot collide with any existing directory in the destination
tree. The operator then explicitly copies from staging → destination
via named commands.

**Trigger:** Any delivery whose payload includes files in directories
that already exist in the destination tree (e.g., `utils/`, `scripts/`,
`docs/`, `frontend/web/src/`).

**Mechanism:** Staging folder name starts with `_batch<N>_payload`
underscore prefix. Extraction yields:

```
repo_root/
  _batch3d_payload/
    utils/...
    scripts/...
    docs/...
```

Operator then runs explicit copies:

```cmd
copy /Y _batch3d_payload\utils\core.py utils\core.py
xcopy /E /I /Y _batch3d_payload\frontend\web\src frontend\web\src
```

And ONLY THEN removes the staging folder:

```cmd
rmdir /S /Q _batch3d_payload
```

**What this protocol prevents:** the `utils/` directory deletion
false-alarm during Batch 3b extraction. The original delivery placed
`utils/auth_jwt.py` and `utils/api.py` at the ZIP root, where Windows
ZIP extraction merged them into the existing `utils/` directory. The
operator's subsequent `xcopy /Y utils\*.py utils\` resolved both
source and destination to the same folder, failing with "File cannot
be copied onto itself". The operator then ran `rmdir /S /Q utils`
expecting to delete an extraction artifact — but the artifact had
merged into the real `utils/`, so the rmdir deleted ~100 source files.
Recovery via `git checkout HEAD -- utils/` was clean, but the incident
demonstrates the cost.

**Codified during:** Batch 3d (post-incident, after the false alarm
in Batch 3b's recovery flow).

---

## Backup-before-mutation discipline

**Rule:** Any script that mutates sensitive credential or state data
files (`data/users.json`, `data/audit_log.json`, similar) MUST create
a timestamped backup before the mutation. The backup file name follows
the pattern `<original>.pre_<operation>_YYYYMMDD_HHMMSS`. The backup
pattern is gitignored to prevent backups from reaching origin.

**Trigger:** Any code path that writes to a file containing credentials,
hashed passwords, secrets, audit records, or other sensitive state.

**Mechanism:** Per `scripts/verify_bcrypt.py:write_backup()` reference
implementation. Backup happens BEFORE the temp-file write that
precedes atomic rename. If backup fails, the script aborts BEFORE
mutating — disk/permission issues must be resolved before the operator
retries.

**Codified during:** Batch 3d (after Batch 3c's initial migration
shipped without an automatic backup, requiring the operator to make a
manual `copy` after the fact — band-aid recovery that wouldn't be
remembered by the next operator).

**Reference implementation:**

```python
def write_backup(path: Path) -> Path:
    import datetime as _dt
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_suffix(path.suffix + f".pre_envelope_{stamp}")
    backup_path.write_text(path.read_text(encoding="utf-8"),
                           encoding="utf-8")
    return backup_path
```

---

## Silent-except is a latent bug

**Rule:** A bare `except Exception: pass` is a defect waiting to be
discovered. Every silent swallow MUST be replaced with logged exception
handling that preserves availability (does not re-raise) but makes the
failure observable.

**Trigger:** Code review encountering any `except Exception: pass` (or
similar bare swallow). Existing instances are remediated as found, not
deferred.

**Mechanism:**

```python
# WRONG — silent swallow
try:
    risky_operation()
except Exception:
    pass

# RIGHT — observable swallow
try:
    risky_operation()
except Exception as e:
    logger.error(
        "Operation FAILED — context: %s; "
        "exception: %s: %s",
        relevant_context, type(e).__name__, e,
        exc_info=True,
    )
    # Optional: do not re-raise if availability is primary
```

**Codified during:** Batch 3d (after Batch 3b's discovery of the
`_hash_password` NameError that had been silently swallowed in
`UserManager.authenticate()` for ~2 years).

**SECURITY constraint on log content:** Logs about credential-handling
code paths must NEVER include plaintext passwords, hashes, sha256
derivations, bcrypt strings, tokens, or stack locals containing auth
material. Username + exception class + traceback is sufficient.
Reference: `UserManager.authenticate()` post-Batch-3c.

---

## CGR1 — Reality grounds doctrine

**Rule:** Documents in `docs/architecture/` describe runtime
behavior, not aspiration. When code and doctrine diverge, code wins
and doctrine is updated. Drift events are recorded in
`GOVERNANCE_REALITY_INDEX.md`'s "CGR1 Reality-Check Correction"
section.

**Trigger:** Any time a Claude session inspects code and finds it
contradicts a doctrine document. Trigger ALSO fires when a Claude
session is about to author work against doctrine that hasn't been
inspected in this session.

**Mechanism:** Inspect code → compare to doctrine → if drift exists,
update doctrine to match runtime and record the correction.

**Codified during:** v10.498 Stage C Batch 1b (`5bbc669`).
**Major corrections to date:**
- Stage C Batch 2a — `require_role` factory was already ACTIVE (had been
  classified ASPIRATIONAL)
- Stage C Batch 2a — shadcn/ui pivot was ASPIRATIONAL (had been
  classified as shipped)
- Batch 3a — JWT auth uses Bearer header (had been documented as cookie)
- Batch 3b — `must_change_password` was Streamlit-only (now consistent)
- Batch 3b — auto-upgrade SHA-256 → bcrypt was silently broken for
  ~2 years (now instrumented)
- Batch 3c — envelope verify path is a TRANSITIONAL stabilization
  layer (not canonical end-state; retirement criteria in `POLICY_GAPS.md`)
- Batch 3d — Phase 1 React auth substrate complete; classifications
  refreshed accordingly

---

## Append-only ledger discipline (RL1)

**Rule:** Entries in `REVIVAL_LEDGER.md` are never deleted. Corrections
are themselves new entries citing the original.

**Codified during:** v10.497 (introduction of REVIVAL_LEDGER itself).

This protocol is included here for cross-reference; the canonical
statement is in `REVIVAL_LEDGER.md::Doctrine::RL1`.

---

## Intentionally-tracked credential data

**Rule:** `data/users.json` is listed in `.gitignore` AND is tracked
in git. This apparent inconsistency is intentional. Do NOT run
`git rm --cached data/users.json` to "fix" it.

**Trigger:** Any code review, automated lint, or fresh-eyes session
that notices the entry in `.gitignore` and proposes to either
remove the entry OR un-track the file.

**Why the inconsistency exists:**

The file is currently tracked because the bootstrap-from-generator
workflow (Path A in `POLICY_GAPS.md` GAP-002) hasn't been designed.
A fresh clone needs `data/users.json` present for `UserManager` to
initialise; un-tracking would force every fresh clone to either
run `generate_staff_v2.py` first OR restore the file from a secure
source. Both are legitimate workflows; neither has been built.

The `.gitignore` entry exists because if the file is ever removed
from the working tree (during a deliberate switch to Path A, or
during ad-hoc operator workflow), it prevents `git add .` from
silently re-adding it before the operator decides whether the
absence was intentional.

**The contents are bcrypt-wrapped, not plaintext.** Post-v10.497
the file stores bcrypt hashes via `UserManager.hash_pw`. Post-v10.500
Batch 3c, 1437 previously-SHA-256 hashes are wrapped in bcrypt
envelopes via `scripts/verify_bcrypt.py`. The pre-v10.497 "plaintext
credentials" wording in the original `.gitignore` comment was
misleading; corrected in Batch 4c.

**Codified during:** v10.501 Phase 2 Arc C Batch 4c (closure of
GAP-002 via Path B accept-and-document).

**Future migration path (Path A — bootstrap-from-generator):**
When repo privacy posture changes (e.g. open-sourcing parts of the
codebase, or shared development across organisations), Path A
becomes necessary. The arc:

1. Design first-run README with explicit `python generate_staff_v2.py`
   step and operator-data sync mechanism.
2. Run `git rm --cached data/users.json` and commit.
3. Update this section to remove the "tracked" status and add the
   first-run prerequisite to the operational checklist.
4. Verify on a fresh clone that the new bootstrap workflow produces
   a usable system without manual intervention.

Until that arc lands, Path B is the active doctrine.

**Sibling rule — backup files MUST stay gitignored.** The patterns
`data/users.json.pre_*`, `data/users.json.post_*_migration`, and
`data/users.json.batch3c_tmp` are correctly gitignored and must
remain so. Those files contain credential material from
backup-before-mutation operations (Batch 3c/3d discipline) and have
no legitimate path into git history.

---

## Single-worker FastAPI operational constraint

**Rule:** The FastAPI API tier (`utils/api.py`) MUST be deployed as a
single uvicorn worker. Multi-worker deployment is a breaking change
that requires switching the slowapi rate-limit storage backend from
in-memory to a shared cache (Redis or memcached).

**Trigger:** Any deployment artifact, scaling proposal, or
infrastructure change that would invoke `uvicorn` with
`--workers N` where N > 1.

**Mechanism (positive):** Single worker means every request hits the
same Python process, which means slowapi's in-memory counters are
authoritative across all requests. A login attempt that bumps the
per-IP counter to 9 is visible to the same counter on attempt 10
because there's only one counter.

**Mechanism (failure mode if violated):** Two workers means two
independent in-memory counters. An attacker hitting `/api/auth/login`
gets a fresh 10-per-minute budget on each worker the load balancer
routes them to. With N workers and a round-robin balancer, the
effective budget becomes N × 10 per minute — and audit logging
still fires, so the operator sees lots of `API_LOGIN_FAILED` rows
but no `API_RATE_LIMITED` rows until each worker individually
fills its bucket. GAP-006 closure regression.

**Codified during:** v10.501 Phase 2 Arc B Batch 4b (introduction of
slowapi rate limiting).

**How to verify in production:** the uvicorn invocation in
`run_all.bat` (or equivalent deployment script) must use the default
single-worker mode OR explicitly pass `--workers 1`. Any deployment
documentation should make this constraint explicit and reference this
section.

**Future migration path (when multi-worker becomes necessary):**
1. Introduce Redis or memcached as a shared cache backend
2. Switch `Limiter(...)` instantiation in `utils/api.py` to use
   `storage_uri="redis://..."` or `"memcached://..."` instead of the
   default in-memory backend
3. Add the cache service to deployment topology
4. Add health checks and failover behaviour (if Redis goes down, do
   we fail-open or fail-closed on auth rate limiting?)
5. Remove this operational constraint section as RESOLVED
6. Update `tests/test_rate_limit_auth.py` to use a fakeredis fixture
   instead of `limiter.reset()`

This is a single-batch arc when it lands; not in scope for Phase 2.

---

## Future protocol candidates (under consideration)

These have not yet been codified but may be added in Phase 2:

- **`_APP_VERSION` stamp policy.** When and how to bump the version
  stamp in `app.py`. Currently arbitrary; could be tied to batch
  milestones via a mechanical check.
- **Mandatory regression test per closure gate.** Phase 1 had 10
  closure gates; only 1 (Gate #8 envelope INFO log) shipped a
  regression test, and that was added retroactively in Batch 3d.
  Phase 2 could mandate a test ships in the SAME batch that claims
  a gate closed.
- **Pre-commit hook for gitignore violations.** Currently relies on
  manual `git status` review. A pre-commit hook checking against the
  Batch 3d-added gitignore patterns would catch `users.json.pre_*`
  or `users.json.post_*_migration` files before they reach the index.
- **Doctrine staleness audit gate.** A gate that compares
  `SESSION_BOOTSTRAP.md::Last commit on main` to actual `git log -1`
  and fails if they diverge by more than N batches.

---

## How to invoke a protocol in conversation

In a fresh chat, the operator or Claude can reference these protocols
by name without re-explaining:

- "Trap #11 — let me inspect before answering."
- "Trap #12 — packaging as ZIP."
- "Trap #14 — using `_batch4a_payload` namespace."
- "Backup-before-mutation — script will write a timestamped backup
  first."
- "Silent-except is a latent bug — let me find what's swallowing this."

The userMemory captures the existence of these protocols; this document
is their canonical specification.
