# Phase B Continuity — Auth-Store Concurrency Bug (2026-06-26)

**Committed HEAD:** `1541e74` (Phase B2). Clean. B3 and B4 were attempted and
**rolled back** (both failed their gates). `utils/core.py` restored to B2 via
`git checkout`. The tree on core.py is clean.

## Banked today (all committed, pushed, harness 295/295)
- `56921e7` Phase A — race-free atomic deal IDs (PG sequence).
- `aab93a7` Phase B0 — _db_sync persists all 17 deal fields; PG is a complete
  mirror (round-trip proven).
- `1541e74` Phase B2 — _get_or_hydrate_deal reads PG-first. Fixed the
  double-advance crash (Probe 3: 500 -> consistent), reduced concurrent-update
  403s 7/10 -> 3/10. RESIDUAL recorded in that commit.

## Attempts that FAILED their gate (rolled back, NOT committed)
- **B3 (atomic _save_deals):** made the concurrency profile WORSE — create-500s
  10/20 -> 16/20, 403s 3/10 -> 7/10. Root reason: the JSON whole-file write is
  the wrong primitive; making it atomic added fsync/replace contention without
  fixing the race. Disproved "corruption is the cause." Rolled back.
- **B4 (retry the users.json read):** no improvement (enrichment still 8/10
  fail). Disproved "the read throws under concurrency." Rolled back.

## THE BUG — narrowed by measurement to one surface

Symptom: under concurrent PUTs, 7/10 return 403 "outside your cascade scope" on
deals the caller owns. Traced through the stack:

  get_current_user -> _enrich_identity_from_store (auth_jwt.py:224) ->
  UserManager() -> if staff_code not filled -> get_visible_staff_codes returns
  empty set -> cascade scope check denies -> 403.

`diag_b4_enrich` PROVED `_enrich_identity_from_store` fails to fill staff_code
**7-8/10 under concurrency** (matches the 7/10 PUT 403s exactly).

### Eliminated by direct instrumentation (all clean under concurrency):
1. Pipeline-deal read — `diag_b4_instrument`: 10/10 PG-ok, staff_code 300731.
2. Roster + get_visible_staff_codes — `diag_b4_user`: 0/10 missing owner.
3. Create timing — `diag_b4_isolate`: deals settle 10/10, 403s persist after 3s.
4. users.json FILE read — `diag_b4_why`: 0/10 missing frank, n_users=70 every
   read, parse_ok every time, even with 4 writer threads churning. The FILE IS
   ALWAYS COMPLETE. The read is NOT the problem. The write is NOT truncating.

### The remaining (unexamined) surface — NEXT SESSION STARTS HERE:
`_enrich_identity_from_store` reads the file fine, but it calls `UserManager()`,
whose `__init__` does MORE than `_load`:

    def __init__(self):
        self.users_file = DATA_DIR / "users.json"
        self.users = self._load()
        self.ensure_test_logins()          # <-- calls add_user + save_users()
        self.ensure_branch_test_logins()   # <-- calls add_user + save_users()

The contradiction to resolve: the raw file read is always complete (70 users,
frank present) — `diag_b4_why` — yet `UserManager().users.get("frank0731")`
returns empty 8/10 — `diag_b4_enrich`. So the loss happens INSIDE construction,
AFTER _load, in the ensure_* self-heal path, which on every per-request
construction can `add_user` + `save_users()` (a non-atomic write) and mutate
`self.users`. Under concurrency these self-heal writes race each other and the
per-request reads.

HYPOTHESIS for next session (instrument before fixing — do NOT assume):
  Some concurrent construction's ensure_* sees a transiently-incomplete
  self.users (or a save_users mid-write from another instance) and either
  rewrites users.json with a reduced set or leaves self.users without frank,
  so the .get("frank0731") in enrichment misses.

### Fix directions to evaluate NEXT SESSION (pick after instrumenting __init__):
1. **Don't construct UserManager per request for read-only enrichment.** A
   process-wide cached/singleton user store (mtime-refreshed) read under a lock,
   so enrichment never triggers a write and never races construction. This is
   the most likely correct fix — enrichment is a READ; it should never write.
2. Make `save_users()` atomic (temp+fsync+os.replace) AND make the ensure_*
   self-heal NOT run on every construction (only on an explicit seed/admin path),
   so a normal authenticated request never writes users.json.
3. A module-level lock around UserManager construction/save.

### Gate for any fix (the B3/B4 lesson — harness-green is NOT proof):
- `diag_b4_enrich.py` enrichment failures must go 8/10 -> 0/10.
- `diag_concurrent_update.py` 403s must go 7/10 -> ~0.
- `simulate_credit_chain.py` must stay 295/295.
Ship ONLY if the 403s actually fall.

## Diagnostic scripts (all on disk under scripts/, keep them)
diag_b4_isolate.py, diag_b4_instrument.py, diag_b4_user.py, diag_b4_enrich.py,
diag_b4_why.py, diag_concurrent_update.py, stress_concurrency.py.

## STILL-OPEN concurrency holes (separate from the 403 bug, all Phase C):
- Probe 2 lost-updates (the 3/10 that pass scope but don't persist) — the
  genuine pipeline-deal JSON write race. Needs PG-authoritative update writes
  (atomic UPDATE...WHERE, not pm.get_deal after racy _save_deals).
- create-500s under load — same JSON whole-file write race.
- These are NOT the 403 bug. The 403 bug is auth-store (users.json) construction.

## KEY LESSON THIS SESSION
The "concurrent-update data loss" was misdiagnosed from the start (original
Phase 4 + my B2/B3) as pipeline-deal persistence. Instrumentation proved the
DOMINANT failure (7/10 403s) is the AUTH IDENTITY store: per-request
UserManager() construction racing its own self-heal writes. Four candidate
mechanisms eliminated by measurement before the real surface was isolated.
Reason-ahead-of-measurement produced 3 wrong fixes (B3, B4, and two mis-scoped
B4 hypotheses). Instrument the construction internals FIRST next session.
