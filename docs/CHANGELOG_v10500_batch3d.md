# CHANGELOG — v10.500 Phase 1 Batch 3d

**Date:** 2026-05-26
**Predecessor commit:** Batch 3c (bcrypt envelope migration)
**Doctrine in force:** CGR1 (reality-grounding), Traps #11 (no fabrication), #12 (no paste cascade), #14 (no path-colliding extractions — codified this batch), backup-before-mutation discipline (codified this batch), silent-except-is-a-latent-bug doctrine (codified this batch)

---

## Summary

**Closes Phase 1.** All 10 closure gates green. Refreshes doctrine
artifacts that accumulated drift across batches 3a/3b/3c, closes the
verify_pw envelope-INFO-log observability gap with a 5-test regression
suite, codifies the operational protocols that emerged during Phase 1
into a new constitutional artifact (`OPERATIONAL_PROTOCOL.md`), and
records the stated-vs-enforced policy gaps as Phase 2 candidates in a
new tracked artifact (`POLICY_GAPS.md`).

This batch is the doctrine-and-hygiene capstone for Phase 1. No
architectural changes; no new features; the only code changes are
`scripts/verify_bcrypt.py` (timestamped backup before mutation) and
`tests/test_verify_pw_observability.py` (regression coverage).

---

## Phase 1 closure status (10/10 green)

| Gate | Status | Closed by |
|---|---|---|
| 1. Real user opens app | ✅ | Batch 3a |
| 2. Redirect to /login | ✅ | Batch 3a |
| 3. Authenticate | ✅ | Batch 3a |
| 4. Receive token | ✅ | Batch 3a |
| 5. Refresh page, stay authenticated | ✅ | Batch 3a |
| 6. Access protected routes | ✅ | Batch 3a |
| 7. Logout cleanly | ✅ | Batch 3a |
| 8. Dormant SHA-256 migration path | ✅ | Batch 3c (functional) + Batch 3d (observability regression) |
| 9. `must_change_password` consistent Streamlit + FastAPI | ✅ | Batch 3b |
| 10. Doctrine artifacts refreshed | ✅ | Batch 3d (this batch) |

---

## Files shipped (10 total)

| # | Path | Action | Lines (approx.) |
|---|---|---|---|
| 1 | `.gitignore` | MODIFY | +30 (runtime audit logs, backup patterns) |
| 2 | `scripts/verify_bcrypt.py` | MODIFY | +40 (write_backup function + integration into write_users) |
| 3 | `tests/test_verify_pw_observability.py` | NEW | ~190 |
| 4 | `docs/continuity/SESSION_BOOTSTRAP.md` | REWRITE | ~180 (full refresh from commit `49e804f` → `216171d`) |
| 5 | `docs/architecture/REVIVAL_LEDGER.md` | MODIFY | +100 (4 new entries: 3d, 3c, 3b, 3a in reverse chrono) |
| 6 | `docs/architecture/GOVERNANCE_REALITY_INDEX.md` | MODIFY | +50 (CGR1 reality-check correction for Phase 1 React substrate) |
| 7 | `docs/architecture/OPERATIONAL_PROTOCOL.md` | NEW | ~230 |
| 8 | `docs/architecture/POLICY_GAPS.md` | NEW | ~180 |
| 9 | `docs/CHANGELOG_v10500_batch3d.md` | NEW | this file |
| 10 | `app.py` | MODIFY | 1 line (`_APP_VERSION` bump) |

---

## Doctrine added or codified

### `OPERATIONAL_PROTOCOL.md` (NEW)

Constitutional artifact codifying:

- **Trap #11** — No fabrication (every claim grounded in same-turn inspection)
- **Trap #12** — No paste cascade (ZIP for multi-file deliveries)
- **Trap #14** — No path-colliding extractions (namespaced staging folders)
- **Backup-before-mutation** — sensitive-data scripts write timestamped backup before mutation
- **Silent-except-is-a-latent-bug** — every `except Exception: pass` MUST be replaced with logged exception handling
- **CGR1** — Reality grounds doctrine (cross-reference; canonical in SYSTEM_CONSTITUTION.md)

Each protocol has a defined trigger, mechanism, and historical context
showing when it was codified and what mistake it prevents.

### `POLICY_GAPS.md` (NEW)

Tracks 7 known intentional divergences between stated and enforced
policy:

- GAP-001: Password complexity advertised but not enforced
- GAP-002: `data/users.json` gitignored but tracked
- GAP-003: Envelope verify path has no retirement criteria
- GAP-004: `must_rotate` tokens have no shorter inactivity timeout
- GAP-005: Streamlit `force_change_pw` doesn't require current password
- GAP-006: No rate limiting on auth endpoints
- GAP-007: `_APP_VERSION` stamp is informational only

Each entry includes status (OPEN / DEFERRED / CLOSED), stated location,
enforced location, risk, and Phase 2 recommendation.

---

## Code changes

### `scripts/verify_bcrypt.py` — backup-before-mutation

Adds `write_backup(path)` function and calls it from `write_users(path)`
BEFORE the atomic temp-file rename. Backup file naming:
`data/users.json.pre_envelope_YYYYMMDD_HHMMSS`.

If backup fails, the script aborts BEFORE mutating — disk/permission
issues must be resolved before retry.

The backup pattern (`data/users.json.pre_*`, `data/users.json.post_*_migration`)
is added to `.gitignore` in this batch so backups never reach origin.

**Rationale:** Batch 3c's initial migration shipped without an
automatic backup mechanism; the operator had to make a manual `copy`
after the migration completed (good band-aid, bad doctrine — the next
operator wouldn't think to do it). This codifies the protection.

### `tests/test_verify_pw_observability.py` — 5 regression tests

Closes the verification gap from Batch 3c: the envelope INFO log
("Envelope-backed credential authenticated") was implemented correctly
but not proven to fire (test user `william001` was reset to direct
bcrypt during rotation testing, never took the envelope path).

Tests:

1. **`test_envelope_path_emits_info_log_with_username`** — envelope
   verify success WITH username kwarg emits one INFO log identifying
   the user
2. **`test_envelope_path_emits_info_log_without_username`** — same,
   without username kwarg (backward-compat call sites still emit, just
   without identifier)
3. **`test_direct_bcrypt_does_NOT_emit_envelope_log`** — common path
   stays quiet (no log noise)
4. **`test_wrong_password_against_envelope_does_NOT_emit_log`** —
   failed verifies don't conflate signal and noise
5. **`test_wrong_password_against_direct_bcrypt_does_NOT_emit_log`** —
   symmetry check

All 5 pass against the Batch 3c `utils/core.py`. The envelope
observability hook works as designed.

### `app.py` — `_APP_VERSION` bump

```diff
- _APP_VERSION = "1.0.0-2026.04.13"
+ _APP_VERSION = "v10.500-phase1-closed-2026.05.26"
```

Marks the Phase 1 milestone in the version stamp. The stamp wipes
stale manager objects on app reload (per `app.py` header), so the bump
also flushes any session state holding stale references.

### `.gitignore` — runtime files + backup patterns

Adds:
- `data/audit_log.json` — runtime mutation log, should never have been tracked
- `data/audit_trail.jsonl` — same
- `data/users.json.pre_*`, `data/users.json.post_*_migration` — backup patterns
- `*.pre_batch*_hotfix` — generic backup pattern
- `utils/*.pre_*`, `utils/*.preBatch*` — hotfix backup patterns

**Follow-up step the operator can run on their own schedule** (NOT
applied in this commit):

```cmd
git rm --cached data/audit_log.json
git rm --cached data/audit_trail.jsonl
git commit -m "Untrack runtime audit files (Batch 3d follow-up)"
```

This removes the already-tracked copies from the index while keeping
the local files. Future modifications won't appear in `git status`.

---

## Verification checklist

- [x] `scripts/verify_bcrypt.py` parses cleanly
- [x] `tests/test_verify_pw_observability.py` parses cleanly
- [x] All 5 tests in `test_verify_pw_observability.py` pass against
       Batch 3c `utils/core.py`
- [x] `SESSION_BOOTSTRAP.md` references current commit
       (`216171d`) and reflects Phase 1 closure
- [x] `REVIVAL_LEDGER.md` has chronological entries for all 4 Phase 1
       batches (newest first)
- [x] `GOVERNANCE_REALITY_INDEX.md` includes CGR1 reality-check
       correction for Phase 1 React substrate completion
- [x] `OPERATIONAL_PROTOCOL.md` codifies Traps #11, #12, #14 + backup
       discipline + silent-except doctrine
- [x] `POLICY_GAPS.md` records 7 known gaps with Phase 2
       recommendations
- [x] `_APP_VERSION` in app.py bumped

---

## After commit — operator follow-ups

These are optional, on the operator's schedule:

1. **Untrack runtime audit files:**
   ```cmd
   git rm --cached data/audit_log.json
   git rm --cached data/audit_trail.jsonl
   git commit -m "Untrack runtime audit files (Batch 3d follow-up)"
   ```

2. **Push to origin** (all 4 Phase 1 batches together):
   ```cmd
   git push origin main
   ```
   Local commits `13d5258`, `2aab56b`, `216171d-prev`, and `216171d`
   land on origin in one push.

3. **Delete the Batch 3a leftover:**
   ```cmd
   del HOTFIX_NOTE.md
   ```

4. **Remove the migration backup** (only after confidence in the
   new state is established — e.g., 30 days of running auth without
   incident):
   ```cmd
   del data\users.json.post_batch3c_migration
   ```

---

## Phase 1 retrospective notes

**What worked:**

- ZIP-based delivery workflow (Trap #12) eliminated copy-paste errors
- Pre-batch inspection (Trap #11) caught 8 errors in original Phase 1
  prose spec at Batch 3a's start
- CGR1 grounded each batch in actual runtime, preventing accumulated
  drift
- Per-batch git commits with detailed messages made the arc reviewable
- Operator's incremental verification at each batch caught the
  hash_pw NameError in Batch 3b before it shipped

**What surprised us:**

- The 2-year-old NameError hidden under `except Exception: pass` —
  discovered only because Batch 3b exercised the un-swallowed code
  path (codified as the "silent-except is a latent bug" doctrine)
- The `utils/` directory deletion false-alarm during Batch 3b
  extraction — codified as Trap #14
- The credential drift in the userMemory's transcript summary
  (`ECOStaff001` vs `EcoStaff0001`) — reinforced Trap #11
- The verify_pw envelope INFO log "not firing" turning out to be a
  wrong-test-user issue, not a code defect — reinforced "test the
  right thing, not the convenient thing"

**What's left for Phase 2:**

See `POLICY_GAPS.md` for the 7 tracked gaps. See `SESSION_BOOTSTRAP.md`
"Active workstreams" for the broader workstream list. Stage C
governance enforcement resumes; React substrate Phase 2 features
(settings, voluntary password change, password reset UX) are
candidates; envelope retirement criteria become actionable once log
aggregation is in place.

---

**End of CHANGELOG — v10.500 Phase 1 Batch 3d**
**Phase 1 closed.**
