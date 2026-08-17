#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RL1 - a bank administrator stops being "Staff".

FROM THE PILOT (2026-08-12): saving a committee in admin returned 403 for
somebody who is genuinely an administrator, on a screen share - so not a matter
of the wrong person clicking.

THE CAUSE. _claims() defaults a missing role to "Staff", and
_enrich_identity_from_store did not carry `role` at all. It filled staff_code,
full_name, is_admin, department and the managed_* lists - but not the one field
every permission gate reads. A token without a role claim therefore made that
person Staff for the whole session, whatever their user record said, and
require_config_admin refused them.

That is why it hit the pilot and not this side: the AD login does not
necessarily put a role in the token; the Postgres-backed login here does.

THE FIX. `role` joins the enrichment list, and "Staff" is treated as unset for
that key - it is a DEFAULT, not an assertion. A token that really does carry a
role still wins, so a genuine claim stays authoritative over the store.

Measured:

    token "Staff", store "Systems Administrator"
        -> Systems Administrator, config-admin: True
    token "Relationship Manager", store "Systems Administrator"
        -> Relationship Manager, config-admin: False

THE SAME SHAPE AS TWO OTHER FAULTS TODAY - a gate reading a value never
populated the way it expected: _analyst_segment called without a staff code,
an audit reading a config file instead of the accessor, and now a role
defaulting to a placeholder nothing matches. Worth checking any other gate that
reads a field the token may not carry.

Usage (from project root, .venv active):
    python scripts\\patch_rl1_role_from_store.py            # dry run
    python scripts\\patch_rl1_role_from_store.py --apply
"""
import os
import shutil
import sys

AUTH = os.path.join("utils", "auth_jwt.py")
BACKUP_SUFFIX = ".pre_rl1"

OLD = '''        for key in ("staff_code", "full_name", "can_view_all", "is_admin",
                    "managed_staff_codes", "managed_roles", "managed_units",
                    "department"):
            if key in rec and (key not in user or user.get(key) in (None, "")):
                user[key] = rec[key]'''

NEW = r'''        # ── ROLE IS ENRICHED TOO, AND "Staff" COUNTS AS UNSET ──────────────
        # A token without a role claim gets "Staff" from _claims(), and role
        # was NOT in this list - so that placeholder stuck for the session and
        # every role gate refused the person. An AD login that does not carry a
        # role turned a bank administrator into Staff, which is why saving a
        # committee returned 403 for somebody who is genuinely an admin.
        #
        # "Staff" is a DEFAULT, not an assertion. Treating it as unset lets the
        # store answer, while a token that really does carry a role still wins
        # - a claim is still authoritative over the store.
        for key in ("staff_code", "full_name", "can_view_all", "is_admin",
                    "managed_staff_codes", "managed_roles", "managed_units",
                    "department", "role"):
            _blank = (None, "")
            if key == "role":
                _blank = (None, "", "Staff", "staff")
            if key in rec and (key not in user or user.get(key) in _blank):
                user[key] = rec[key]'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(AUTH):
        print("ABORT: %s not found." % AUTH)
        return 1

    src = open(AUTH, encoding="utf-8").read()
    if "ROLE IS ENRICHED TOO" in src:
        print("ABORT: RL1 looks applied.")
        return 1
    if src.count(OLD) != 1:
        print("ABORT: the enrichment block matched %d times." % src.count(OLD))
        return 1

    src = src.replace(OLD, NEW, 1)
    print("  ok  role enriched from the store")

    if '"role"' not in NEW:
        print("ABORT: role is still not enriched.")
        return 1
    if '"Staff"' not in NEW:
        print("ABORT: the 'Staff' placeholder would still block enrichment, so")
        print("       an AD login with no role claim stays Staff.")
        return 1
    if "user.get(key) in _blank" not in NEW:
        print("ABORT: the store would overwrite a genuine role claim.")
        return 1
    print("  ok  post-checks: Staff treated as unset, real claims still win")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(AUTH, AUTH + BACKUP_SUFFIX)
    open(AUTH, "w", encoding="utf-8", newline="").write(src)
    print("APPLIED %s" % AUTH)

    import py_compile
    try:
        py_compile.compile(AUTH, doraise=True)
        print("  ok  auth_jwt.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Restart uvicorn. EVERYONE MUST SIGN OUT AND BACK IN - a session")
    print("already holding 'Staff' keeps it until the next login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
