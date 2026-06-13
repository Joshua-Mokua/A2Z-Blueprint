# CHANGELOG v10.546 — Phase P Batch P-AUTH-b: UserManager._load hardening

Root-cause fix for the disappearing test logins.

## Problem
UserManager._load() had `except: return self._defaults()`, and _defaults()
immediately _save()s. So ANY transient read error or partial/corrupt write
silently overwrote users.json with the 3 default accounts — destroying the
real/seeded accounts (this is how william001 + the 49 role logins vanished).

## Fix (utils/core.py)
_load now distinguishes:
  - absent / empty file            -> first run, defaults are correct
  - exists but unreadable / not-JSON -> back up to users.json.corrupt-<tag>-<ts>,
    log loudly, and RAISE (never overwrite a recoverable real file)
New helper _backup_unreadable() (best-effort; never masks the original error).

## Test (tests/test_p_auth_b_load_hardening.py)
- source-scan: bare silent fallback is gone, backup helper present
- behavioral: corrupt file preserved + backup made + raises; empty -> defaults;
  valid file with william001 survives

## Verification
- py_compile utils/core.py -> OK
- standalone control-flow proof (absent/empty/valid/corrupt) -> all correct
- behavioral pytest runs in the full-deps env (Josh)
