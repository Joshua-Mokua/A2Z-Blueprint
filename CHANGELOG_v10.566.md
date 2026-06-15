# CHANGELOG v10.566 — fix: branch test logins must be hashed (login was declined)

## Problem
v10.563's seed wrote plaintext "password": "EcoStaff0720" directly to
users.json. The React login path (UserManager.authenticate -> verify_pw)
accepts ONLY bcrypt, envelope-bcrypt, or SHA-256 hex — there is no plaintext
path — so every branch login was declined.

## Fix
scripts/seed_branch_test_logins.py now creates accounts via
UserManager.add_user(), which bcrypt-hashes the password through hash_pw —
identical to the canonical seed (scripts/seed_test_logins.py). add_user also
sets active=True and must_change_password=False; region/_protected are set
after, then save_users().

Idempotent: re-running REPAIRS the existing plaintext rows (add_user overwrites
the account with a properly hashed credential). Still backs up users.json
(timestamped) first and aborts if it's missing/empty.

--list remains dependency-free (register read only) for quick inspection.

## Action
Re-run the seed to repair the accounts, then log in:
    python scripts/seed_branch_test_logins.py --branch Thika
