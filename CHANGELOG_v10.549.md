# CHANGELOG v10.549 — Phase P Batch P-AUTH-c: login resilience (root cause)

The disappearing test logins were a DIRECTORY problem, not a code bug:
DATA_DIR = Path("data") is relative, so the users.json that gets read/
written depends on the process working directory. A nested duplicate tree
(a2z/a2z/, untracked) with an older un-hardened core.py and its own
users.json could shadow the real one depending on where the app was
launched, so seeds written to <repo>/data were not what the running app read.

## Fix (utils/core.py)
1. DATA_DIR is now ABSOLUTE, anchored to core.py's own location:
   `(Path(__file__).resolve().parent.parent / "data")`. The launch folder
   can no longer decide which users.json is used.
2. UserManager gains ensure_test_logins(), called from __init__: if the
   canonical CEO login (william001) is missing it is recreated (active,
   no-rotation, _protected). Cheap membership check; writes only when a
   restore was actually needed. UserManager is built per request, so this
   self-heals on the very next request after any reset.

## Test (tests/test_p_auth_c_resilience.py)
- source-scan: absolute DATA_DIR, self-heal present + called
- behavioral: DATA_DIR absolute; william present after construction;
  ensure_test_logins idempotent when present, restores when missing

## Operational (do these locally, see commit instructions)
- gitignore the untracked nested tree (a2z/a2z/) and ideally delete it,
  so the un-hardened twin can never be imported by accident.

## Verification
- py_compile core.py -> OK
- proof: DATA_DIR resolves to <repo>/data regardless of CWD; self-heal
  restores-when-missing / no-op-when-present (0 writes) -> all pass
