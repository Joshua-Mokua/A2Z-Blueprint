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
